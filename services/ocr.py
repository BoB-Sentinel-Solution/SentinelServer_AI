# services/ocr.py
# OCR 비활성 스텁: 항상 미사용 처리로 반환
from typing import Tuple
from schemas import InItem  # 타입 힌트용 (없어도 동작엔 영향 없음)

class OcrService:
    @staticmethod
    def needs_ocr(item: InItem) -> Tuple[bool, str]:
        """과거 호환용: 항상 미사용으로 간주"""
        return (False, "ocr_disabled")

    @staticmethod
    def run_ocr(item: InItem) -> Tuple[str, bool, str]:
        """
        Returns:
            ocr_text: ""
            ocr_used: False
            engine_info: "ocr_disabled"
        """
        return ("", False, "ocr_disabled")
