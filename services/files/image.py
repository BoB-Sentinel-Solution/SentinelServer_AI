# services/files/image.py
from __future__ import annotations

from typing import Tuple

from .types import FileProcessResult


def run_ocr_image(path) -> Tuple[bool, str, str]:
    """
    이미지용 OCR 수행.
    실제 구현 시 Tesseract, PaddleOCR 등과 연동.

    return: (used, text, error)
      - used: OCR 시도 여부
      - text: OCR 결과 텍스트 (성공 시)
      - error: 에러 메시지 or "" (없으면)
    """
    # TODO: 실제 OCR 붙일 때 여기 구현
    return False, "", "ocr_disabled"


def process_image_file(result: FileProcessResult) -> FileProcessResult:
    """
    이미지(png/jpg/jpeg/webp)에 대해 ② OCR 수행.
    """
    used, text, err = run_ocr_image(result.saved_path)

    result.ocr_used = used
    result.extracted_text = text if used and text else ""
    result.ocr_error = err or None
    return result
