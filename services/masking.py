# services/masking.py
from __future__ import annotations
from typing import List, Dict, Tuple
import re

# schemas.Entity가 상황에 따라 속성이 다를 수 있음:
# - 구버전(정규식): label, begin, end
# - 신버전(AI):     type, value
from schemas import Entity

# 토큰 매핑 (없으면 라벨/타입 그대로 토큰으로 사용)
TOKEN: Dict[str, str] = {
    # 1) Basic Identity Information
    "NAME": "NAME",
    "PHONE": "PHONE",
    "EMAIL": "EMAIL",
    "ADDRESS": "ADDRESS",
    "POSTAL_CODE": "POSTAL_CODE",

    # 2) Public Identification Number
    "PERSONAL_CUSTOMS_ID": "PERSONAL_CUSTOMS_ID",
    "RESIDENT_ID": "RESIDENT_ID",
    "PASSPORT": "PASSPORT",
    "DRIVER_LICENSE": "DRIVER_LICENSE",
    "FOREIGNER_ID": "FOREIGNER_ID",
    "HEALTH_INSURANCE_ID": "HEALTH_INSURANCE_ID",
    "BUSINESS_ID": "BUSINESS_ID",
    "MILITARY_ID": "MILITARY_ID",

    # 3) Authentication Information
    "JWT": "JWT",
    "API_KEY": "API_KEY",
    "GITHUB_PAT": "GITHUB_PAT",
    "PRIVATE_KEY": "PRIVATE_KEY",

    # 4) Financial Information
    "CARD_NUMBER": "CARD_NUMBER",
    "CARD_EXPIRY": "CARD_EXPIRY",
    "BANK_ACCOUNT": "BANK_ACCOUNT",
    "CARD_CVV": "CARD_CVV",
    "PAYMENT_PIN": "PAYMENT_PIN",
    "MOBILE_PAYMENT_PIN": "MOBILE_PAYMENT_PIN",

    # 5) Crypto
    "MNEMONIC": "MNEMONIC",
    "CRYPTO_PRIVATE_KEY": "CRYPTO_PRIVATE_KEY",
    "HD_WALLET": "HD_WALLET",
    "PAYMENT_URI_QR": "PAYMENT_URI_QR",

    # 6) Network
    "IPV4": "IPV4",
    "IPV6": "IPV6",
    "MAC_ADDRESS": "MAC_ADDRESS",
    "IMEI": "IMEI",

    # 구버전 호환
    "ORDER_ID": "ORDER_ID",
    "PASSWORD": "PASSWORD",
    "USERNAME": "USERNAME",
    "CARD_NO": "CARD_NUMBER",
}

def _norm_label(e: Entity) -> str:
    # 구버전: e.label / 신버전: e.type
    lbl = getattr(e, "label", None) or getattr(e, "type", None) or ""
    return str(lbl).strip().upper()

def _token_for(label: str) -> str:
    lab = (label or "").upper()
    return TOKEN.get(lab, lab or "SENSITIVE")

def _collect_ranges_by_offset(original: str, entities: List[Entity]) -> List[Tuple[int, int, str]]:
    """구버전(label, begin, end) 엔티티에서 교체 범위 수집"""
    ranges: List[Tuple[int, int, str]] = []
    for e in entities:
        if hasattr(e, "begin") and hasattr(e, "end"):
            try:
                b = int(getattr(e, "begin"))
                en = int(getattr(e, "end"))
            except Exception:
                continue
            if 0 <= b < en <= len(original):
                ranges.append((b, en, _token_for(_norm_label(e))))
    return ranges

def _collect_ranges_by_value(original: str, entities: List[Entity]) -> List[Tuple[int, int, str]]:
    """신버전(type, value) 엔티티에서 값 매칭으로 범위 수집(중복 비겹치게 탐색)"""
    ranges: List[Tuple[int, int, str]] = []
    taken = [False] * (len(original) + 1)  # 간단한 겹침 방지 마크
    for e in entities:
        val = getattr(e, "value", None)
        if not val:
            continue
        pat = re.escape(str(val))
        for m in re.finditer(pat, original):
            b, en = m.span()
            # 겹침이면 스킵
            if any(taken[b:en]):
                continue
            # 마크하고 추가
            for i in range(b, en):
                taken[i] = True
            ranges.append((b, en, _token_for(_norm_label(e))))
    return ranges

def _merge_and_sort(ranges: List[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """겹치는 구간 최소화(겹치면 더 긴 구간 우선), 이후 뒤에서 앞으로 치환할 수 있게 정렬"""
    if not ranges:
        return []
    # 시작 오름차순, 길이 내림차순으로 정렬 후 non-overlap 선택
    ranges = sorted(ranges, key=lambda x: (x[0], -(x[1] - x[0])))
    merged: List[Tuple[int, int, str]] = []
    taken: List[Tuple[int, int]] = []
    for b, en, tok in ranges:
        overlap = any(not (en <= tb or te <= b) for tb, te in taken)
        if overlap:
            continue
        taken.append((b, en))
        merged.append((b, en, tok))
    # 실제 치환은 뒤에서 앞으로
    merged.sort(key=lambda x: x[0], reverse=True)
    return merged

def _apply_ranges(original: str, ranges: List[Tuple[int, int, str]], parens: bool) -> str:
    s = original
    for b, en, tok in ranges:
        rep = f"({tok})" if parens else tok
        s = s[:b] + rep + s[en:]
    return s

def _prepare_ranges(original: str, entities: List[Entity]) -> List[Tuple[int, int, str]]:
    """오프셋 우선, 값 기반을 보강으로 합쳐 겹침 정리까지 완료"""
    if not original or not entities:
        return []
    ranges = _collect_ranges_by_offset(original, entities)
    if not ranges:
        ranges = _collect_ranges_by_value(original, entities)
    else:
        ranges += _collect_ranges_by_value(original, entities)
    return _merge_and_sort(ranges)

def mask_by_entities(original: str, entities: List[Entity]) -> str:
    """
    엔티티를 토큰으로 치환 (괄호 없음).
    """
    ranges = _prepare_ranges(original, entities)
    if not ranges:
        return original
    return _apply_ranges(original, ranges, parens=False)

def mask_with_parens_by_entities(original: str, entities: List[Entity]) -> str:
    """
    엔티티를 '(TOKEN)'으로 치환 (괄호 포함).
    """
    ranges = _prepare_ranges(original, entities)
    if not ranges:
        return original
    return _apply_ranges(original, ranges, parens=True)
