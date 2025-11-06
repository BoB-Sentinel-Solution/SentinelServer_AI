# services/db_logging.py
from __future__ import annotations

import uuid, time
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from schemas import InItem, ServerOut, Entity
from models import LogRecord
from services.ocr import OcrService
from services.masking import mask_by_entities
from services.attachment import save_attachment_file
from services.similarity import best_similarity_against_folder
from repositories.log_repo import LogRepository

from services.detect import analyze_with_entities  # 옵션 A

ADMIN_IMAGE_DIR = Path("./SentinelServer_AI/adminset/image")
SIMILARITY_THRESHOLD = 0.4  # 이미지 유사도 차단 임계

class DbLoggingService:
    @staticmethod
    def _serialize_attachment(att) -> Dict[str, Any] | None:
        if att is None:
            return None
        if hasattr(att, "model_dump"):
            return att.model_dump()
        if hasattr(att, "dict"):
            return att.dict()
        return None

    @staticmethod
    def handle(db: Session, item: InItem) -> ServerOut:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())

        # 1) 첨부 저장
        saved_info = save_attachment_file(item)  # -> (path, mime) or None
        saved_path: Path | None = None
        saved_mime: str | None = None
        if saved_info:
            saved_path, saved_mime = saved_info

        # 2) OCR
        ocr_text, ocr_used, _ = OcrService.run_ocr(item)

        # 3) AI 감지 (프롬프트 / OCR)
        prompt_text = item.prompt or ""
        try:
            det_prompt = analyze_with_entities(prompt_text)
        except Exception:
            det_prompt = {"has_sensitive": False, "entities": [], "processing_ms": 0}

        prompt_entities = det_prompt.get("entities", [])
        det_ocr_ms = 0
        ocr_entities: List[Dict[str, Any]] = []
        if ocr_used and ocr_text:
            try:
                det_ocr = analyze_with_entities(ocr_text)
                ocr_entities = det_ocr.get("entities", [])
                det_ocr_ms = int(det_ocr.get("processing_ms", 0))
            except Exception:
                ocr_entities = []
                det_ocr_ms = 0

        has_sensitive = bool(det_prompt.get("has_sensitive") or ocr_entities)
        ai_ms = int(det_prompt.get("processing_ms", 0)) + det_ocr_ms

        # 4) 정책결정 (이미지 유사도 포함)
        file_blocked = False
        allow = True
        action = "mask_and_allow" if prompt_entities else "allow"

        if (
            saved_mime
            and saved_mime.startswith("image/")
            and ocr_used
            and (not ocr_text or len(ocr_text.strip()) < 3)
        ):
            try:
                if saved_path and ADMIN_IMAGE_DIR.exists():
                    score, ref = best_similarity_against_folder(saved_path, ADMIN_IMAGE_DIR)
                    if score >= SIMILARITY_THRESHOLD:
                        file_blocked = True
                        allow = False
                        action = "block_upload_similar"
            except Exception:
                pass

        # 5) 마스킹(프롬프트만)
        # Entity 모델로 검증 후 마스킹에 전달
        masked_entities = []
        for e in prompt_entities:
            try:
                masked_entities.append(Entity(**e))
            except Exception:
                # 라벨/스팬 불완전시 스킵
                pass

        modified_prompt = mask_by_entities(prompt_text, masked_entities)

        # 전체 처리시간
        processing_ms = max(int((time.perf_counter() - t0) * 1000), ai_ms)

        # hostname 우선, 없으면 pc_name/pcname 대체
        host_name = item.hostname or getattr(item, "pc_name", None) or getattr(item, "PCName", None)

        # 6) DB 저장
        rec = LogRecord(
            request_id      = request_id,
            time            = item.time,
            public_ip       = item.public_ip,
            private_ip      = item.private_ip,
            host            = item.host or "unknown",
            hostname        = host_name,
            prompt          = prompt_text,
            attachment      = DbLoggingService._serialize_attachment(item.attachment),
            interface       = item.interface or "llm",

            modified_prompt = modified_prompt,
            has_sensitive   = has_sensitive,
            entities        = [dict(e) for e in prompt_entities],  # 프롬프트 엔티티만 저장/표시
            processing_ms   = processing_ms,

            file_blocked    = file_blocked,
            allow           = allow,
            action          = action,
        )
        LogRepository.create(db, rec)

        # 7) 응답
        return ServerOut(
            request_id      = request_id,
            host            = rec.host,
            modified_prompt = rec.modified_prompt,
            has_sensitive   = rec.has_sensitive,
            entities        = [Entity(**e) for e in rec.entities if set(e).issuperset({"value","begin","end","label"})],
            processing_ms   = rec.processing_ms,
            file_blocked    = rec.file_blocked,
            allow           = rec.allow,
            action          = rec.action,
        )
