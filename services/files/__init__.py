from __future__ import annotations

from services.attachment import SavedFileInfo
from .types import FileProcessResult, IMAGE_EXTS, DOC_EXTS
from . import document as document_handlers
from .redaction import redact_saved_file, RedactedFileInfo


def process_saved_file(saved: SavedFileInfo) -> FileProcessResult:
    """
    Sentinel Server 파일 처리 공통 진입점.

    ① 다운로드
       - attachment.py에서 base64 → 실제 파일 저장 후 SavedFileInfo 로 전달

    ② 텍스트 추출 (텍스트 기반 문서만)
       - DOCX / PPTX / XLSX / TXT / CSV:
         services/files/document.py 에서 파일을 직접 열어
         정규식(regex_rules.PATTERNS)으로 중요정보를 탐지·라벨 토큰으로 치환한
         *.detection.* 파일을 생성하고, 치환된 전체 텍스트를 extracted_text 에 채움.
       - PDF / 이미지(PNG/JPG/WEBP)는 여기서 텍스트 추출을 하지 않고,
         services/files/redaction.py 의 redact_saved_file() 로
         좌표 기반 레댁션/래스터 마스킹을 수행한다.

    ③ 중요 정보 탐지 / 레댁션
       - 문자열 기반 탐지는 regex_rules, masking 모듈에서,
       - 이미지·PDF 좌표 기반 레댁션은 redaction.py 에서 처리.

    이 함수는 ②까지(텍스트 기반 문서에 대한 추출·치환)만 담당하고,
    반환된 FileProcessResult.extracted_text 를 상위 서비스에서 사용한다.
    """

    result = FileProcessResult.from_saved(saved)

    # 항상 normalize 된 ext 사용 (점 없음, 소문자)
    ext = (result.ext or "").lower()

    # 텍스트 기반 문서(DOCX / PPTX / XLSX / TXT / CSV)만 처리
    if ext in DOC_EXTS and ext != "pdf":
        # document_handlers.process_document_file 이 내부에서
        # *.detection.* 파일을 생성하고, 텍스트를 추출/치환해서
        # result.extracted_text / result.ocr_used / result.ocr_error 를 채운다.
        result = document_handlers.process_document_file(result)
    else:
        # 이미지, PDF, 그 외 확장자는 여기서는 별도 텍스트 추출을 하지 않음.
        # (필요시 redact_saved_file(saved) 를 별도로 호출해서 사용)
        result.ocr_used = False
        result.ocr_error = None

    return result
