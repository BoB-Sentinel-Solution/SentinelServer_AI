import time, uuid
from fastapi import APIRouter
from schemas import InItem, ServerOut
from services.ocr import OcrService
from services.detect import detect_entities, has_sensitive_any
from services.masking import mask_by_entities

router = APIRouter()

@router.get("/healthz")
def healthz():
    return {"ok": True}

@router.post("/logs", response_model=ServerOut)
def ingest(item: InItem) -> ServerOut:
    t0 = time.perf_counter()

    # 1) OCR 판단 & 실행
    ocr_text, ocr_used, ocr_reason = OcrService.run_ocr(item)

    # 2) 텍스트 탐지(프롬프트 기준)
    prompt_text = item.prompt or ""
    prompt_entities = detect_entities(prompt_text)

    # 3) OCR 텍스트에서도 별도 탐지 (파일 민감도 판단용)
    ocr_entities = detect_entities(ocr_text) if ocr_used and ocr_text else []

    # 4) 민감여부 및 파일 정책
    has_sensitive = has_sensitive_any(prompt_entities, ocr_entities)

    # 파일 차단 정책:
    # - OCR 수행했고 OCR에서 민감 발견 => 파일 업로드 차단
    # - 그 외에는 업로드 허용 (프롬프트는 마스킹 후 allow)
    if ocr_used and ocr_entities:
        file_blocked = True
        allow = False
        action = "block_upload"
    else:
        file_blocked = False
        allow = True
        # 프롬프트에 민감이 있으면 마스킹 후 allow
        action = "mask_and_allow" if prompt_entities else "allow"

    # 5) modified_prompt (프롬프트만 마스킹; OCR 텍스트는 프롬프트에 미반영)
    modified_prompt = mask_by_entities(prompt_text, prompt_entities)

    processing_ms = int((time.perf_counter() - t0) * 1000)

    return ServerOut(
        request_id=str(uuid.uuid4()),
        host=item.host or "unknown",
        modified_prompt=modified_prompt,
        has_sensitive=has_sensitive,
        entities=prompt_entities,      # 위치(begin/end)는 프롬프트 기준
        processing_ms=processing_ms,
        file_blocked=file_blocked,
        allow=allow,
        action=action,
    )
