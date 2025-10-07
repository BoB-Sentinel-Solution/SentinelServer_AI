# services/attachment.py
from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import base64
import re

from schemas import InItem

# 간단한 확장자 매핑 (필요 시 확장)
_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "application/pdf": ".pdf",
}

def _sanitize(s: str) -> str:
    # 경로에 안전하도록 최소 정규화
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", s or "unknown")

def save_attachment_file(
    item: InItem,
    downloads_root: Path = Path("./SentinelServer_AI/downloads")
) -> Optional[Tuple[Path, str]]:
    """
    첨부(b64)가 있으면 파일을 디스크에 저장하고 (경로, mime) 반환.
    없으면 None.
    저장 경로: ./SentinelServer_AI/downloads/{public_ip}/{hostname}/YYYYMMDD_HHMMSS.ext
    """
    att = item.attachment
    if not att or not att.format or not att.data:
        return None

    mime = att.format.lower().strip()
    ext = _MIME_TO_EXT.get(mime, "")
    subdir = downloads_root / _sanitize(item.public_ip or "noip") / _sanitize(item.hostname or "noname")
    subdir.mkdir(parents=True, exist_ok=True)

    # 파일명: 시간 기반 + 확장자
    # time 문자열의 콜론 등 제거
    stem = _sanitize(item.time)
    if not ext:
        # 확장자 유추 못하면 기본 .bin
        ext = ".bin"

    out_path = subdir / f"{stem}{ext}"

    raw = base64.b64decode(att.data)
    out_path.write_bytes(raw)
    return (out_path.resolve(), mime)
