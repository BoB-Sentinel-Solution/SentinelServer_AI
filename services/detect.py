# services/detect.py
from __future__ import annotations
from typing import Any, Dict, List
import time

from services.ai_detector import analyze_text

ALLOWED = {
    "NAME","PHONE","EMAIL","ADDRESS","POSTAL_CODE",
    "PERSONAL_CUSTOMS_ID","RESIDENT_ID","PASSPORT","DRIVER_LICENSE","FOREIGNER_ID","HEALTH_INSURANCE_ID","BUSINESS_ID","MILITARY_ID",
    "JWT","API_KEY","GITHUB_PAT","PRIVATE_KEY",
    "CARD_NUMBER","CARD_EXPIRY","BANK_ACCOUNT","CARD_CVV","PAYMENT_PIN","MOBILE_PAYMENT_PIN",
    "MNEMONIC","CRYPTO_PRIVATE_KEY","HD_WALLET","PAYMENT_URI_QR",
    "IPV4","IPV6","MAC_ADDRESS","IMEI",
}

def _index_all(hay: str, needle: str) -> List[int]:
    """hay에서 needle의 모든 시작 인덱스 반환(겹침 허용 안함)"""
    res = []
    if not hay or not needle:
        return res
    start = 0
    L = len(needle)
    while True:
        i = hay.find(needle, start)
        if i == -1: break
        res.append(i)
        start = i + L
    return res

def analyze_with_entities(text: str) -> Dict[str, Any]:
    """
    반환:
      {
        "has_sensitive": bool,
        "entities": [{"value","begin","end","label"}, ...],
        "processing_ms": int
      }
    """
    t0 = time.time()
    ai = analyze_text(text or "")
    has_sensitive = bool(ai.get("has_sensitive", False))
    entities_out: List[Dict[str, Any]] = []

    for e in ai.get("entities", []):
        label = str(e.get("type","")).upper()
        value = str(e.get("value",""))
        if not label or not value: 
            continue
        if label not in ALLOWED:
            continue

        for idx in _index_all(text or "", value):
            entities_out.append({
                "value": value,
                "begin": idx,
                "end": idx + len(value),
                "label": label
            })

    ms = int((time.time() - t0) * 1000)
    # 안전장치: has_sensitive가 True라면 최소 1개라도 엔티티가 남도록 보정(없으면 False 처리)
    if has_sensitive and not entities_out:
        has_sensitive = False

    return {"has_sensitive": has_sensitive, "entities": entities_out, "processing_ms": ms}
