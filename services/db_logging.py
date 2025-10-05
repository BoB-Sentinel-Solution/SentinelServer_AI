# services/db_logging.py
import uuid, time
from sqlalchemy.orm import Session
from schemas import InItem, ServerOut, Entity
from models import LogRecord
from services.ocr import OcrService
from services.detect import detect_entities, has_sensitive_any
from services.masking import mask_by_entities
from repositories.log_repo import LogRepository

class DbLoggingService:
    """
    - OCR 판단/실행 → 탐지 → 정책결정 → 마스킹
    - 요청+결과를 단일 레코드로 DB 저장
    - ServerOut 응답 반환
    """
    @staticmethod
    def handle(db: Session, item: InItem) -> ServerOut:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())

        # OCR
        ocr_text, ocr_used, _ = OcrService.run_ocr(item)

        # 탐지
        prompt_text = item.prompt or ""
        prompt_entities = detect_entities(prompt_text)
        ocr_entities    = detect_entities(ocr_text) if ocr_used and ocr_text else []
        has_sensitive   = has_sensitive_any(prompt_entities, ocr_entities)

        # 정책
        if ocr_used and ocr_entities:
            file_blocked, allow, action = True, False, "block_upload"
        else:
            file_blocked = False
            allow = True
            action = "mask_and_allow" if prompt_entities else "allow"

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
