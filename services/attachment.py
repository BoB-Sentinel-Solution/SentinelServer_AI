# services/attachment.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import base64
import re

from schemas import InItem

# 지원하는 확장자 → MIME 매핑
# format 필드에는 확장자만 온다고 가정 (예: "png", "pdf", "docx" ...)
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
    """파일/디렉터리 이름에 쓸 문자열을 최소한으로 정규화."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", s or "unknown")


def save_attachment_file(
    item: InItem,
    downloads_root: Path = Path("./SentinelServer_AI/downloads"),
) -> Optional[Tuple[Path, str]]:
    """
    첨부(b64)가 있으면 파일을 디스크에 저장하고 (경로, mime) 반환.
    없으면 None.
    저장 경로: ./SentinelServer_AI/downloads/{public_ip}/{hostname}/YYYYMMDD_HHMMSS.ext

    - item.attachment.format  : 확장자 (예: "png", "pdf", "docx")
    - item.attachment.data    : base64 인코딩된 파일 데이터
    """
    att = item.attachment
    if not att or not att.format or not att.data:
        return None

    # 1) 확장자 정규화 (대소문자/앞의 점 제거)
    fmt = att.format.strip().lower()  # "PNG" → "png"
    if fmt.startswith("."):
        fmt = fmt[1:]

    # 2) MIME / 확장자 결정
    mime: str = _EXT_TO_MIME.get(fmt, "")
    ext: str = f".{fmt}" if fmt else ""

    # 지원하지 않는 확장자이거나 format이 비어 있으면 .bin 으로 저장
    if not ext:
        ext = ".bin"

    # 3) 저장 디렉터리 구성: downloads_root / {public_ip} / {hostname}
    subdir = (
        downloads_root
        / _sanitize(item.public_ip or "noip")
        / _sanitize(item.hostname or "noname")
    )
    subdir.mkdir(parents=True, exist_ok=True)

    # 4) 파일명: time 기반 + 확장자
    stem = _sanitize(item.time)
    if not stem:
        stem = "unknown_time"

    out_path = subdir / f"{stem}{ext}"

    # 5) base64 디코딩 후 파일로 저장
    raw = base64.b64decode(att.data)
    out_path.write_bytes(raw)

    # saved_path, saved_mime 형식으로 반환
    return (out_path.resolve(), mime)
