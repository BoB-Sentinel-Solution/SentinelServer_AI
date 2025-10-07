# services/db_logging.py
import uuid, time
from pathlib import Path
from sqlalchemy.orm import Session
from schemas import InItem, ServerOut, Entity
from models import LogRecord
from services.ocr import OcrService
from services.detect import detect_entities, has_sensitive_any
from services.masking import mask_by_entities
from services.attachment import save_attachment_file
from services.similarity import best_similarity_against_folder
from repositories.log_repo import LogRepository

ADMIN_IMAGE_DIR = Path("./SentinelServer_AI/adminset/image")
SIMILARITY_THRESHOLD = 0.4  # 요청 기준

class DbLoggingService:
    """
    - 첨부 저장(있으면)
    - OCR → 탐지 → 정책결정 → (이미지&OCR무텍스트면 유사도 검사→차단) → 마스킹
    - DB 저장 → 응답
    """
    @staticmethod
    def handle(db: Session, item: InItem) -> ServerOut:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())

        saved_info = save_attachment_file(item)  # (path, mime) or None
        saved_path: Path | None = None
        saved_mime: str | None = None
        if saved_info:
            saved_path, saved_mime = saved_info

        # OCR
        ocr_text, ocr_used, _ = OcrService.run_ocr(item)

        # 탐지 (프롬프트 + OCR 텍스트)
        prompt_text = item.prompt or ""
        prompt_entities = detect_entities(prompt_text)
        ocr_entities    = detect_entities(ocr_text) if ocr_used and ocr_text else []
        has_sensitive   = has_sensitive_any(prompt_entities, ocr_entities)

        # 기본 정책
        file_blocked = False
        allow = True
        action = "mask_and_allow" if prompt_entities else "allow"

        # ★ 이미지 첨부인데 OCR이 돌았지만 텍스트가 거의 없는 경우 → 유사도 검사
        #    - saved_mime가 image/* 이고
        #    - ocr_used True 이지만 ocr_text가 비었거나 길이가 매우 짧다면(노이즈 수준)
        if (
            saved_mime
            and saved_mime.startswith("image/")
            and ocr_used
            and (not ocr_text or len(ocr_text.strip()) < 3)
        ):
            try:
                if saved_path and ADMIN_IMAGE_DIR.exists():
                    score, ref = best_similarity_against_folder(saved_path, ADMIN_IMAGE_DIR)
                    # print(f"[DEBUG] similarity score={score:.3f}, ref={ref}")
                    if score >= SIMILARITY_THRESHOLD:
                        file_blocked = True
                        allow = False
                        action = "block_upload_similar"
            except Exception as e:
                # 유사도 검사 실패는 차단 사유가 아님(로깅만)
                # print(f"[WARN] similarity check failed: {e}")
                pass

        # 마스킹
        modified_prompt = mask_by_entities(prompt_text, prompt_entities)
        processing_ms = int((time.perf_counter() - t0) * 1000)

        # DB 저장
        rec = LogRecord(
            request_id      = request_id,
            time            = item.time,
            public_ip       = item.public_ip,
            private_ip      = item.private_ip,
            host            = item.host or "unknown",
            hostname        = item.hostname,
            prompt          = prompt_text,
            attachment      = (item.attachment.dict() if item.attachment else None),
            interface       = item.interface or "llm",
            modified_prompt = modified_prompt,
            has_sensitive   = has_sensitive,
            entities        = [e.dict() for e in prompt_entities],  # 프롬프트 기준
            processing_ms   = processing_ms,
            file_blocked    = file_blocked,
            allow           = allow,
            action          = action,
        )
        LogRepository.create(db, rec)

        # 응답
        return ServerOut(
            request_id      = request_id,
            host            = rec.host,
            modified_prompt = rec.modified_prompt,
            has_sensitive   = rec.has_sensitive,
            entities        = [Entity(**e) for e in rec.entities],
            processing_ms   = rec.processing_ms,
            file_blocked    = rec.file_blocked,
            allow           = rec.allow,
            action          = rec.action,
        )
