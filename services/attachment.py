# services/attachment.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import base64
import re

from schemas import InItem

_EXT_TO_MIME = {
    # 이미지
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",

    # 문서
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv":  "text/csv",
    "txt":  "text/plain",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _sanitize(s: str) -> str:
    s = s or "unknown"
    # 윈도우 호환: ':' → '-'
    s = s.replace(":", "-")
    # 나머지 이상한 문자들은 '_'로
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


@dataclass
class SavedFileInfo:
    ext: str
    mime: str
    path: Path


def save_attachment_file(
    item: InItem,
    downloads_root: Path = Path("./downloads"),
) -> Optional[SavedFileInfo]:
    att = getattr(item, "attachment", None)
    if not att or not att.format or not att.data:
        return None

    fmt = att.format.strip().lower()
    if fmt.startswith("."):
        fmt = fmt[1:]

    ext = fmt
    mime = _EXT_TO_MIME.get(ext, "")

    # downloads_root는 여기서부터 lazily 생성됨
    subdir = (
        downloads_root
        / _sanitize(item.public_ip or "noip")
        / _sanitize(item.hostname or item.pc_name or "noname")
    )
    subdir.mkdir(parents=True, exist_ok=True)

    stem = _sanitize(item.time) or "unknown_time"
    suffix = f".{ext}" if ext else ".bin"
    out_path = subdir / f"{stem}{suffix}"

    raw = base64.b64decode(att.data)
    out_path.write_bytes(raw)

    return SavedFileInfo(
        ext=ext,
        mime=mime,
        path=out_path.resolve(),
    )
