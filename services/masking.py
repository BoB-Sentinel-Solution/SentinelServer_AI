# services/masking.py
from typing import List, Dict
from schemas import Entity

_LABEL_TOKEN: Dict[str, str] = {
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "ORDER_ID": "ORDER_ID",
    "PASSWORD": "PASSWORD",
    "USERNAME": "USERNAME",
    "CARD_NO": "CARD_NO",
}

def mask_by_entities(original: str, entities: List[Entity]) -> str:
    if not entities or not original:
        return original
    s = original
    for ent in sorted(entities, key=lambda e: e.begin, reverse=True):
        token = _LABEL_TOKEN.get(ent.label, ent.label)
        s = s[:ent.begin] + token + s[ent.end:]
    return s
