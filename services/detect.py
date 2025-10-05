from typing import List
from schemas import Entity

def detect_sensitive_text(text: str) -> (bool, List[Entity]):
    """
    TODO: AI/정규식/규칙엔진으로 교체.
    현재는 단순 예시: 'password', IPv4 토큰 추정
    """
    hits: List[Entity] = []
    low = (text or "").lower()

    if "password" in low or "비밀번호" in low:
        hits.append(Entity(type="password", value="***matched***"))

    for token in low.replace(",", " ").split():
        if token.count(".") == 3 and all(p.isdigit() for p in token.split(".")):
            hits.append(Entity(type="pii", value=token))

    return (bool(hits), hits)
