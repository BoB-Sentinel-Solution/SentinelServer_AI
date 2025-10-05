from typing import List, Dict
from schemas import Entity

# 라벨 → 치환 토큰 매핑
_LABEL_TOKEN: Dict[str, str] = {
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "ORDER_ID": "ORDER_ID",
    # 필요 시 확장 (NAME, ADDRESS, PASSWORD, ...)
}

def mask_by_entities(original: str, entities: List[Entity]) -> str:
    """
    엔티티 위치(begin/end)를 이용해 원문을 토큰으로 치환.
    오프셋 깨짐 방지를 위해 뒤에서 앞으로 치환.
    """
    if not entities or not original:
        return original

    s = original
    # 뒤에서 앞으로 치환
    for ent in sorted(entities, key=lambda e: e.begin, reverse=True):
        token = _LABEL_TOKEN.get(ent.label, ent.label)
        s = s[:ent.begin] + token + s[ent.end:]
    return s
