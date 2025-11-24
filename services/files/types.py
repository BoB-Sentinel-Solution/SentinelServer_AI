from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.attachment import SavedFileInfo


# 어떤 확장자를 이미지/문서로 볼지 정의
# ※ 모두 "점 없는 소문자" 기준으로 관리
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
        """
        SavedFileInfo 로부터 FileProcessResult 기본값 생성.

        - 실제 파일 경로의 suffix 기준으로 확장자 normalize
          (예: ".PNG" → "png")
        - suffix 가 없을 경우 SavedFileInfo.ext 를 보조적으로 사용
        """
        suffix = saved.path.suffix.lower().lstrip(".") if saved.path.suffix else ""
        ext_norm = suffix or (saved.ext or "").lower().lstrip(".")

        return cls(
            ext=ext_norm,
            mime=saved.mime,
            saved_path=saved.path,
        )
