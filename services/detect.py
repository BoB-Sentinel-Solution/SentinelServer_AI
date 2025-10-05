# services/detect.py
import re
from typing import List, Tuple, Dict, Any
from schemas import Entity

# =========================
# (1) 정규식 패턴
# =========================
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(01[016789]-?\d{3,4}-?\d{4})")
# password 키워드 추출: "password: xxx", "패스워드 xxx" 등
_PASSWORD_RE = re.compile(r"(?i)(?:password|패스워드)\s*[:=]?\s*([^\s,;]+)")
# username/id 계정 추출: "id hong_gildong", "계정: user-01"
_USERNAME_RE = re.compile(r"(?i)(?:username|user|id|계정)\s*[:=]?\s*([A-Za-z0-9._-]{3,})")
# 카드번호(공백/하이픈 포함 13~19자리) — 과탐지 위험, 필요 시 비활성화
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# =========================
# (2) 유틸
# =========================
def _add_entity(entities: List[Entity], text: str, span: Tuple[int, int], label: str):
    b, e = span
    if 0 <= b < e <= len(text):
        entities.append(Entity(value=text[b:e], begin=b, end=e, label=label))

def _iter_matches_with_span(pattern: re.Pattern, text: str, group: int = 0):
    """
    group == 0 : 매치 전체 구간 반환
    group > 0  : 특정 캡처 그룹의 값만 대상으로 원문 내 span을 계산해 반환
    """
    for m in pattern.finditer(text):
        if group == 0:
            yield m.span(0)
        else:
            val = m.group(group)
            if not val:
                continue
            # 캡처 그룹의 실제 위치를 원문 근방에서 재탐색
            # (문자열 가공 없이 원문 인덱스 보존 목적)
            start = text.find(val, max(m.start(group) - 2, 0), min(m.end(group) + 2, len(text)))
            if start < 0:
                start = m.start(group)
            yield (start, start + len(val))

# =========================
# (3) 공개 API
# =========================
def detect_entities(text: str) -> List[Entity]:
    """
    EMAIL, PHONE, PASSWORD, USERNAME, CARD_NO 를 규칙 기반으로 탐지.
    begin/end 오프셋은 원문 기준.
    """
    ents: List[Entity] = []
    if not text:
        return ents

    # EMAIL/PHONE: 매치 전체를 엔티티로
    for span in _iter_matches_with_span(_EMAIL_RE, text):
        _add_entity(ents, text, span, "EMAIL")

    for span in _iter_matches_with_span(_PHONE_RE, text, group=1):
        _add_entity(ents, text, span, "PHONE")

    # PASSWORD/USERNAME: 값 부분만 엔티티로 (group=1)
    for span in _iter_matches_with_span(_PASSWORD_RE, text, group=1):
        _add_entity(ents, text, span, "PASSWORD")

    for span in _iter_matches_with_span(_USERNAME_RE, text, group=1):
        _add_entity(ents, text, span, "USERNAME")

    # CARD_NO: 과탐 방지용 체크
    for span in _iter_matches_with_span(_CARD_RE, text):
        raw = text[span[0]:span[1]]
        digits = re.sub(r"[ -]", "", raw)
        if 13 <= len(digits) <= 19:
            _add_entity(ents, text, span, "CARD_NO")

    # 정렬(시작 위치 오름차순, 끝 큰 것 우선)
    ents.sort(key=lambda e: (e.begin, -e.end))
    return ents

def has_sensitive_any(prompt_entities: List[Entity], ocr_entities: List[Entity]) -> bool:
    """
    프롬프트/첨부(OCR) 어느 한 쪽이라도 민감 엔티티가 있으면 True
    """
    return bool(prompt_entities or ocr_entities)
