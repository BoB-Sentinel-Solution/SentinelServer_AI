# services/regex_detector.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from .regex_rules import PATTERNS

def _luhn_ok(s: str) -> bool:
    digits = [c for c in s if c.isdigit()]
    if not digits:
        return False
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
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

def _pick_email_group(m) -> Tuple[str, int, int]:
    """
    EMAIL 정규식은 번호 그룹(1|2)로 이메일만 캡처.
    그룹 1 → 2 → 전체 매치 순으로 value/span 선택.
    """
    if getattr(m, "lastindex", None):
        for gi in (1, 2):
            if gi <= m.lastindex:
                try:
                    v = m.group(gi)
                    if v:
                        b, e = m.span(gi)
                        return v, b, e
                except IndexError:
                    pass
    # 폴백: 전체 매치
    v0 = m.group(0)
    b0, e0 = m.span(0)
    return v0, b0, e0

def detect_entities(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []

    found: List[Tuple[int, int, str, str]] = []  # (b, e, label, value)

    for label, rx in PATTERNS.items():
        for m in rx.finditer(text):
            # ===== EMAIL만 캡처 그룹으로 값/오프셋 산출 =====
            if label == "EMAIL":
                email_val = None
                gi = None
                # (1) 첫 번째/두 번째 캡처 그룹 중 실제 이메일이 들어있는 쪽 선택
                for i, g in enumerate(m.groups(), start=1):
                    if g:
                        email_val = g
                        gi = i
                        break
                if email_val is not None:
                    b, e = m.start(gi), m.end(gi)
                    val = email_val
                else:
                    # 폴백(이상 상황): 전체 스팬
                    b, e = m.span()
                    val = m.group(0)
            else:
                b, e = m.span()
                val = m.group(0)

            # ===== 선택적 후검증(루한) =====
            if label == "CARD_NUMBER" and not _is_card_pan(val):
                continue
            if label == "IMEI" and not _is_imei(val):
                continue

            found.append((b, e, label, val))

    if not found:
        return []

    # 겹침 정리(긴 스팬 우선)
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    selected: List[Tuple[int, int, str, str]] = []
    taken: List[Tuple[int, int]] = []
    for b, e, lab, val in found:
        if any(not (e <= tb or te <= b) for tb, te in taken):
            continue
        taken.append((b, e))
        selected.append((b, e, lab, val))

    return [{"label": lab, "value": val, "begin": b, "end": e} for b, e, lab, val in selected]

    # 겹침 정리 — 시작 오름차순, 길이 내림차순 정렬 후 non-overlap 선택
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
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
