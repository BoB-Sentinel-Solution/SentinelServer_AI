import base64
import io
from typing import Optional
from PIL import Image

def decode_base64_to_bytes(data_b64: str) -> bytes:
    return base64.b64decode(data_b64)

def load_image_from_base64(data_b64: str) -> Image.Image:
    raw = decode_base64_to_bytes(data_b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")

def is_supported_image_mime(mime: str) -> bool:
    if not mime:
        return False
    mime = mime.lower().strip()
    return mime in {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/bmp", "image/tiff"}

def is_supported_pdf_mime(mime: str) -> bool:
    return (mime or "").lower().strip() == "application/pdf"
