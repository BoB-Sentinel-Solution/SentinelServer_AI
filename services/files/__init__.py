# services/files/__init__.py
from __future__ import annotations

from services.attachment import SavedFileInfo
from .types import FileProcessResult, IMAGE_EXTS, DOC_EXTS
from . import image as image_handlers
from . import document as document_handlers


def process_saved_file(saved: SavedFileInfo) -> FileProcessResult:
    """
    Sentinel Server 파일 처리 공통 진입점.

    ① 다운로드  → (attachment.py에서 이미 수행 완료, SavedFileInfo로 전달)
    ② OCR/텍스트 추출 → 여기서 수행 (확장자별 분기)
    ③ 중요 정보 탐지 → 기존 regex + AI 로직에서 수행
    ④ 레덱션/마스킹 → 기존 masking 로직에서 수행

    여기서는 ②까지만 담당하고,
    반환된 FileProcessResult.extracted_text를 상위 서비스에서 사용.
    """
    result = FileProcessResult.from_saved(saved)
    ext = (saved.ext or "").lower()

    if ext in IMAGE_EXTS:
        # 이미지 파일: OCR
        result = image_handlers.process_image_file(result)
    elif ext in DOC_EXTS:
        # 문서 파일: 텍스트 추출
        result = document_handlers.process_document_file(result)
    else:
        # 지원하지 않는 확장자 (여기 올 일은 거의 없음)
        result.ocr_used = False
        result.ocr_error = f"unsupported_ext:{ext or 'unknown'}"

    return result
