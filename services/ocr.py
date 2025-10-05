from typing import Tuple
from schemas import InItem
from utils.imaging import (
    is_supported_image_mime, is_supported_pdf_mime,
    load_image_from_base64, decode_base64_to_bytes
)

# Optional deps (없으면 우회)
try:
    import pytesseract
    _HAS_TESSERACT = True
except Exception:
    _HAS_TESSERACT = False

try:
    from pdf2image import convert_from_bytes
    _HAS_PDF2IMAGE = True
except Exception:
    _HAS_PDF2IMAGE = False


class OcrService:
    @staticmethod
    def needs_ocr(item: InItem) -> Tuple[bool, str]:
        att = item.attachment
        if not att or not att.format or not att.data:
            return (False, "no_attachment")
        if is_supported_image_mime(att.format):
            return (True, "image")
        if is_supported_pdf_mime(att.format):
            return (True, "pdf")
        return (False, f"unsupported_mime:{att.format}")

    @staticmethod
    def run_ocr(item: InItem) -> Tuple[str, bool, str]:
        """
        Returns: (text, used, reason)
        used=True일 때만 OCR 실행됨.
        """
        need, why = OcrService.needs_ocr(item)
        if not need:
            return ("", False, why)

        if not _HAS_TESSERACT:
            return ("", False, "pytesseract_not_installed")

        fmt = (item.attachment.format or "").lower().strip()
        data_b64 = item.attachment.data

        try:
            if is_supported_image_mime(fmt):
                img = load_image_from_base64(data_b64)
                text = pytesseract.image_to_string(img)
                return (text or "", True, "ocr_image_ok")

            if is_supported_pdf_mime(fmt):
                if not _HAS_PDF2IMAGE:
                    return ("", False, "pdf2image_not_installed")
                pdf_bytes = decode_base64_to_bytes(data_b64)
                pages = convert_from_bytes(pdf_bytes, dpi=200)
                chunks = []
                for p in pages:
                    chunks.append(pytesseract.image_to_string(p))
                return ("\n".join(ch for ch in chunks if ch), True, "ocr_pdf_ok")

            return ("", False, "mime_mismatch")
        except Exception as e:
            return ("", False, f"ocr_error:{e!r}")
