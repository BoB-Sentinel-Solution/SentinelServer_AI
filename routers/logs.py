from fastapi import APIRouter
from schemas import InItem, DetectResponse
from services.ocr import OcrService
from services.detect import detect_sensitive_text

router = APIRouter()

@router.post("/logs", response_model=DetectResponse)
def ingest(item: InItem) -> DetectResponse:
    """
    1) 첨부 존재/포맷에 따라 OCR 필요 여부 판단
    2) 필요하면 OCR → 텍스트 추출
    3) 판별 텍스트 = prompt (+ OCR 텍스트)
    4) (더미) 민감정보 판별 → 요구 포맷으로 응답
    """
    ocr_text, ocr_used, _reason = OcrService.run_ocr(item)

    # 판별에 사용할 텍스트 구성: 프롬프트 + (OCR 결과)
    if ocr_used and ocr_text:
        effective_text = f"{item.prompt}\n\n[OCR]\n{ocr_text}"
    else:
        effective_text = item.prompt

    has_sensitive, entities = detect_sensitive_text(effective_text)

    # NOTE: modified_prompt는 지금은 원문을 그대로 돌려줍니다.
    # 실제 마스킹이 필요해지면 여기서 가공해서 내려주세요.
    return DetectResponse(
        has_sensitive=has_sensitive,
        entities=entities,
        modified_prompt=item.prompt
    )

@router.get("/healthz")
def healthz():
    return {"ok": True}
