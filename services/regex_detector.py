# services/regex_detector.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple
from .regex_rules import PATTERNS

def _luhn_ok(s: str) -> bool:
    digits = [c for c in s if c.isdigit()]
    if not digits:
        return False
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d = d*2 - 9 if d > 4 else d*2
        total += d
        alt = not alt
    return total % 10 == 0

def _is_imei(s: str) -> bool:
    ds = [c for c in s if c.isdigit()]
    return len(ds) == 15 and _luhn_ok(s)

def _is_card_pan(s: str) -> bool:
    ds = [c for c in s if c.isdigit()]
    return 13 <= len(ds) <= 19 and _luhn_ok(s)

def _add_match(out: List[Dict[str, Any]], label: str, begin: int, end: int, value: str):
    out.append({"label": label, "value": value, "begin": begin, "end": end})

def detect_entities(text: str) -> List[Dict[str, Any]]:
    """
    반환: [{label, value, begin, end}, ...]
    과탐 방지를 위해 CARD_NUMBER/IMEI는 루한 검증 통과한 것만 채택.
    겹치는 스팬은 긴 매치 우선으로 정리.
    """
    if not text:
        return []

    found: List[Tuple[int, int, str, str]] = []  # (b, e, label, value)

    for label, rx in PATTERNS.items():
        for m in rx.finditer(text):
            b, e = m.span()
            val = m.group(0)
            # 루한 검증(선택)
            if label == "CARD_NUMBER":
                if not _is_card_pan(val):
                    continue
            if label == "IMEI":
                if not _is_imei(val):
                    continue
            found.append((b, e, label, val))

    if not found:
        return []

    # 겹침 정리 — 시작 오름차순, 길이 내림차순으로 정렬 후 Non-overlap 선택
    found.sort(key=lambda x: (x[0], -(x[1]-x[0])))
    selected: List[Tuple[int, int, str, str]] = []
    taken: List[Tuple[int, int]] = []
    for b, e, lab, val in found:
        overlapped = any(not (e <= tb or te <= b) for tb, te in taken)
        if overlapped:
            continue
        taken.append((b, e))
        selected.append((b, e, lab, val))

    # 결과 변환
    results: List[Dict[str, Any]] = []
    for b, e, lab, val in selected:
        results.append({"label": lab, "value": val, "begin": b, "end": e})
    return results
