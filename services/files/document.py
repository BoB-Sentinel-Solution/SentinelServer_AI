# services/files/document.py
from __future__ import annotations

from typing import Tuple

from .types import FileProcessResult


def extract_text_from_pdf(path) -> Tuple[bool, str, str]:
    """
    PDF 텍스트 추출 / OCR.
    pdfplumber, pymupdf 등과 연동 가능.
    """
    # TODO: 실제 PDF 텍스트 추출 붙일 때 구현
    return False, "", "pdf_text_extraction_disabled"


def extract_text_from_office(path) -> Tuple[bool, str, str]:
    """
    DOCX / PPTX / XLSX 텍스트 추출.
    python-docx / python-pptx / openpyxl 등으로 구현 가능.
    """
    # TODO: 실제 Office 텍스트 추출 붙일 때 구현
    return False, "", "office_text_extraction_disabled"


def extract_text_from_plain(path) -> Tuple[bool, str, str]:
    """
    TXT / CSV: 그냥 UTF-8 텍스트로 읽기.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return True, text, ""
    except Exception as e:
        return False, "", f"plain_text_read_error: {e}"


def process_document_file(result: FileProcessResult) -> FileProcessResult:
    """
    문서(pdf, docx, pptx, csv, txt, xlsx)에 대한 ② 텍스트 추출 담당.
    """
    ext = result.ext

    if ext == "pdf":
        used, text, err = extract_text_from_pdf(result.saved_path)
    elif ext in {"docx", "pptx", "xlsx"}:
        used, text, err = extract_text_from_office(result.saved_path)
    elif ext in {"txt", "csv"}:
        used, text, err = extract_text_from_plain(result.saved_path)
    else:
        used, text, err = False, "", f"unsupported_document_ext:{ext}"

    result.ocr_used = used
    result.extracted_text = text if used and text else ""
    result.ocr_error = err or None
    return result
