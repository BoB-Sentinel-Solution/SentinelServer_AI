# services/files/types.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.attachment import SavedFileInfo


# 어떤 확장자를 이미지/문서로 볼지 정의
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
DOC_EXTS = {"pdf", "docx", "pptx", "csv", "txt", "xlsx"}


@dataclass
class FileProcessResult:
    """
    파일 처리(② OCR/텍스트 추출) 결과.
    ① 다운로드 결과(SavedFileInfo)를 확장한 형태.
    """
    ext: str
    mime: str
    saved_path: Path
    extracted_text: str = ""
    ocr_used: bool = False
    ocr_error: Optional[str] = None

    @classmethod
    def from_saved(cls, saved: SavedFileInfo) -> "FileProcessResult":
        return cls(
            ext=saved.ext,
            mime=saved.mime,
            saved_path=saved.path,
        )
