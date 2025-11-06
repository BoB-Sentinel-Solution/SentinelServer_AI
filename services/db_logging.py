# services/db_logging.py
from __future__ import annotations

import uuid, time, os
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from schemas import InItem, ServerOut, Entity
from models import LogRecord
from services.ocr import OcrService
from services.masking import mask_by_entities
from services.attachment import save_attachment_file
from services.similarity import best_similarity_against_folder
from repositories.log_repo import LogRepository

# 기존 내부 엔진은 비활성화
# from services.detect import analyze_with_entities  # 옵션 A

# 새 외부 판별기 러너
from services.ai_external import OfflineDetectorRunner

ADMIN_IMAGE_DIR = Path("./SentinelServer_AI/adminset/image")
SIMILARITY_THRESHOLD = 0.4  # 이미지 유사도 차단 임계

# 러너 싱글턴 (MODEL_DIR, MAX_NEW_TOKENS는 .env에서 읽힘)
_DETECTOR = OfflineDetectorRunner(
    model_dir=os.environ.get("MODEL_DIR", "").strip() or None,
    timeout_sec=20.0,
)

def _to_labeled_spans(text: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    ai_external의 결과( type/value/(begin/end) ) 를
    서버 공통 스키마(label/value/begin/end)로 매핑.
    """
    out: List[Dict[str, Any]] = []
    for e in entities:
        t = e.get("type") or e.get("label")
        v = e.get("value")
        if not isinstance(t, str) or not isinstance(v, str) or not v.strip():
            continue
        begin = e.get("begin")
        end = e.get("end")
        item = {"label": t.strip().upper(), "value": v.strip()}
        if isinstance(begin, int) and isinstance(end, int):
            item["begin"] = begin
            item["end"] = end
        out.append(item)
    return out

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
        saved_path: Optional[Path] = None
        saved_mime: Optional[str] = None
        if saved_info:
            saved_path, saved_mime = saved_info

        # 2) OCR
        ocr_text, ocr_used, _ = OcrService.run_ocr(item)

        # 3) AI 감지 (프롬프트 / OCR) — 외부 판별기 호출
        prompt_text = item.prompt or ""
        try:
            det_prompt = _DETECTOR.analyze_text(prompt_text, return_spans=True)
        except Exception:
            det_prompt = {"has_sensitive": False, "entities": [], "processing_ms": 0}

        prompt_entities_raw = det_prompt.get("entities", []) or []
        prompt_entities = _to_labeled_spans(prompt_text, prompt_entities_raw)
        det_ocr_ms = 0
        ocr_entities: List[Dict[str, Any]] = []

        if ocr_used and ocr_text:
            try:
                det_ocr = _DETECTOR.analyze_text(ocr_text, return_spans=True)
                ocr_entities_raw = det_ocr.get("entities", []) or []
                # OCR 결과도 label/value/(begin/end)로 정규화
                ocr_entities = _to_labeled_spans(ocr_text, ocr_entities_raw)
                det_ocr_ms = int(det_ocr.get("processing_ms", 0) or 0)
            except Exception:
                ocr_entities = []
                det_ocr_ms = 0

        has_sensitive = bool(det_prompt.get("has_sensitive") or ocr_entities)
        ai_ms = int(det_prompt.get("processing_ms", 0) or 0) + det_ocr_ms

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
        masked_entities: List[Entity] = []
        for e in prompt_entities:
            try:
                # Entity 스키마가 label/value/begin/end 를 기대
                masked_entities.append(Entity(**e))
            except Exception:
                # 라벨/스팬 불완전시 스킵
                pass

        modified_prompt = mask_by_entities(prompt_text, masked_entities)

        # 전체 처리시간
        processing_ms = max(int((time.perf_counter() - t0) * 1000), ai_ms)

        # hostname 우선, 없으면 pc_name/PCName 대체
        host_name = item.hostname or getattr(item, "pc_name", None) or getattr(item, "PCName", None)

        # 6) DB 저장
        rec = LogRecord(
            request_id      = request_id,
            time            = item.time,
            public_ip       = item.public_ip,
            private_ip      = item.private_ip,
            host            = item.host or "unknown",
            host_name       = item.hostname or item.pc_name
            prompt          = prompt_text,
            attachment      = DbLoggingService._serialize_attachment(item.attachment),
            interface       = item.interface or "llm",

            modified_prompt = modified_prompt,
            has_sensitive   = has_sensitive,
            # 프롬프트 엔티티만 저장/표시 (label/value/begin/end 로 정규화된 값 사용)
            entities        = [dict(e) for e in prompt_entities],
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
            # 응답에서도 begin/end/label이 모두 있는 엔티티만 노출
            entities        = [Entity(**e) for e in rec.entities if set(e).issuperset({"value","begin","end","label"})],
            processing_ms   = rec.processing_ms,
            file_blocked    = rec.file_blocked,
            allow           = rec.allow,
            action          = rec.action,
        )
