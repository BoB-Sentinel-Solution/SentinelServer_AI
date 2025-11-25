# services/attachment.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import base64
import re

from schemas import InItem

# 에이전트에서 보내는 확장자 → MIME 매핑
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
    """파일/디렉터리 이름에 쓸 문자열을 최소한으로 정규화.
    
    - 콜론(:)은 윈도우 호환성을 위해 하이픈(-)으로 치환
    - 나머지 허용 문자 외에는 언더스코어(_)로 치환
    """
    s = s or "unknown"
    # 1) 콜론을 먼저 하이픈으로 변환
    s = s.replace(":", "-")
    # 2) 파일명에 쓸 수 있는 안전한 문자만 남기고 나머지는 '_'로 치환
    #    (콜론은 더 이상 허용하지 않음)
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


@dataclass
class SavedFileInfo:
    """attachment를 디스크에 저장한 뒤의 기본 정보."""
    ext: str          # "png", "pdf", "docx" ...
    mime: str         # "image/png", "application/pdf" ...
    path: Path        # 실제 저장된 파일 경로


def save_attachment_file(
    item: InItem,
    downloads_root: Path = Path("./downloads"),
) -> Optional[SavedFileInfo]:
    """
    에이전트에서 넘어온 attachment를 실제 파일로 저장하고 SavedFileInfo를 반환한다.
    (파일 '다운로드' 역할만 수행)

    - item.attachment.format : 확장자 (예: "png", "pdf", "docx")
    - item.attachment.data   : base64 인코딩된 파일 데이터
    """
    att = getattr(item, "attachment", None)
    if not att or not att.format or not att.data:
        return None

    # 1) 확장자 정규화
    fmt = att.format.strip().lower()
    if fmt.startswith("."):
        fmt = fmt[1:]

    ext = fmt
    mime = _EXT_TO_MIME.get(ext, "")

    # 2) 저장 디렉터리 구성: downloads_root / {public_ip} / {hostname}
    subdir = (
        downloads_root
        / _sanitize(item.public_ip or "noip")
        / _sanitize(item.hostname or item.pc_name or "noname")
    )
    subdir.mkdir(parents=True, exist_ok=True)

    # 3) 파일명: time 기반 + 확장자
    #    → time 문자열에 포함된 ':'는 _sanitize 안에서 '-'로 변환됨
    stem = _sanitize(item.time)
    if not stem:
        stem = "unknown_time"

    suffix = f".{ext}" if ext else ".bin"
    out_path = subdir / f"{stem}{suffix}"

    # 4) base64 디코딩 후 파일로 저장
    raw = base64.b64decode(att.data)
    out_path.write_bytes(raw)

    return SavedFileInfo(
        ext=ext,
        mime=mime,
        path=out_path.resolve(),
    )
