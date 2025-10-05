from typing import Tuple
from schemas import InItem
from utils.imaging import (
    is_supported_image_mime, is_supported_pdf_mime,
    load_image_from_base64, decode_base64_to_bytes
)

# pytesseract는 선택 설치. 없으면 graceful fallback.
try:
    import pytesseract
    _has_tesseract = True
except Exception:
    _has_tesseract = False

# PDF → 이미지 변환도 선택 설치
try:
    from pdf2image import convert_from_bytes
    _has_pdf2image = True
except Exception:
    _has_pdf2image = False


class OcrService:
    """
    - needs_ocr: 첨부 존재 + 지원 포맷인지 판정
    - run_ocr: 실제 OCR 실행 (이미지/ PDF)
    """
    @staticmethod
    def needs_ocr(item: InItem) -> Tuple[bool, str]:
        att = item.attachment
        if not att or not att.format or not att.data:
            return (False, "no_attachment")
        mime = att.format.lower().strip()
        if is_supported_image_mime(mime):
            return (True, "image")
        if is_supported_pdf_mime(mime):
            return (True, "pdf")
        return (False, f"unsupported_mime:{mime}")

    @staticmethod
    def run_ocr(item: InItem) -> Tuple[str, bool, str]:
        """
        Returns: (ocr_text, used, reason)
        - used: 실제 OCR 수행 여부
        - reason: 수행/미수행 사유 텍스트
        """
        need, reason = OcrService.needs_ocr(item)
        if not need:
            return ("", False, reason)

        if not _has_tesseract:
            return ("", False, "pytesseract_not_installed")

        mime = item.attachment.format.lower().strip()
        data_b64 = item.attachment.data

        try:
            if is_supported_image_mime(mime):
                img = load_image_from_base64(data_b64)
                text = pytesseract.image_to_string(img)
                return (text or "", True, "ocr_image_ok")

            if is_supported_pdf_mime(mime):
                if not _has_pdf2image:
                    return ("", False, "pdf2image_not_installed")
                pdf_bytes = decode_base64_to_bytes(data_b64)
                pages = convert_from_bytes(pdf_bytes, dpi=200)
                texts = []
                for p in pages:
                    texts.append(pytesseract.image_to_string(p))
                return ("\n".join(filter(None, texts)), True, "ocr_pdf_ok")

            return ("", False, "mime_switched")  # 논리적으로 여기 안 옴

        except Exception as e:
            return ("", False, f"ocr_error:{e!r}")
