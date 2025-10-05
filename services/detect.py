# services/detect.py
import re
from typing import List, Tuple
from schemas import Entity

# (더미) 정규식 기반 탐지기
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(01[016789]-?\d{3,4}-?\d{4})")
_PASSWORD_RE = re.compile(r"(?i)(?:password|패스워드)\s*[:=]?\s*([^\s,;]+)")
_USERNAME_RE = re.compile(r"(?i)(?:username|user|id|계정)\s*[:=]?\s*([A-Za-z0-9._-]{3,})")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")  # 과탐지 주의

def _add_entity(entities: List[Entity], text: str, span: Tuple[int, int], label: str):
    b, e = span
    if 0 <= b < e <= len(text):
        entities.append(Entity(value=text[b:e], begin=b, end=e, label=label))

def _iter_matches_with_span(pattern: re.Pattern, text: str, group: int = 0):
    for m in pattern.finditer(text):
        if group == 0:
            yield m.span(0)
        else:
            val = m.group(group)
            if not val:
                continue
            start = text.find(val, max(m.start(group) - 2, 0), min(m.end(group) + 2, len(text)))
            if start < 0:
                start = m.start(group)
            yield (start, start + len(val))

def detect_entities(text: str) -> List[Entity]:
    ents: List[Entity] = []
    if not text:
        return ents

    for span in _iter_matches_with_span(_EMAIL_RE, text):
        _add_entity(ents, text, span, "EMAIL")

    for span in _iter_matches_with_span(_PHONE_RE, text, group=1):
        _add_entity(ents, text, span, "PHONE")

    for span in _iter_matches_with_span(_PASSWORD_RE, text, group=1):
        _add_entity(ents, text, span, "PASSWORD")

    for span in _iter_matches_with_span(_USERNAME_RE, text, group=1):
        _add_entity(ents, text, span, "USERNAME")

    for span in _iter_matches_with_span(_CARD_RE, text):
        raw = text[span[0]:span[1]]
        digits = re.sub(r"[ -]", "", raw)
        if 13 <= len(digits) <= 19:
            _add_entity(ents, text, span, "CARD_NO")

    ents.sort(key=lambda e: (e.begin, -e.end))
    return ents

def has_sensitive_any(prompt_entities: List[Entity], ocr_entities: List[Entity]) -> bool:
    return bool(prompt_entities or ocr_entities)
