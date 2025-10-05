import re
from typing import List, Tuple
from schemas import Entity

# 간단 정규식 기반 엔티티 탐지 (더미/예시)
_PATTERNS = [
    ("EMAIL", re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),
    ("PHONE", re.compile(r'\b01[0-9]-\d{3,4}-\d{4}\b')),  # 한국 휴대폰 예시
    ("ORDER_ID", re.compile(r'\bORDER-\d{2}-\d{4}-[A-Z]{4}-\d{4}\b')),
    # 필요 시 추가 패턴...
]

def detect_entities(text: str) -> List[Entity]:
    ents: List[Entity] = []
    if not text:
        return ents
    for label, rx in _PATTERNS:
        for m in rx.finditer(text):
            ents.append(Entity(
                value=m.group(0),
                begin=m.start(),
                end=m.end(),
                label=label,
            ))
    # 겹침/중복 정리(간단히 시작위치 기준 정렬)
    ents.sort(key=lambda e: (e.begin, -e.end))
    return ents

def has_sensitive_any(prompt_entities: List[Entity], ocr_entities: List[Entity]) -> bool:
    return bool(prompt_entities or ocr_entities)
