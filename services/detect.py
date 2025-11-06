# services/detect.py
# AI 기반 중요정보 탐지기로 교체 (오프라인 로컬 모델 사용)
from __future__ import annotations

import re
from typing import List, Tuple
from schemas import Entity
from services.ai_detector import analyze_text  # 싱글톤 분석기 (GPU 고정 구성)

def _non_overlapping_spans_by_value(text: str, value: str) -> List[Tuple[int, int]]:
    """
    주어진 value를 원문에서 찾되, 겹치지 않게 순차 매칭.
    여러 번 등장하면 앞에서부터 가능한 곳에 1개씩만 할당.
    """
    if not value:
        return []
    spans: List[Tuple[int, int]] = []
    taken = [False] * (len(text) + 1)
    pat = re.escape(value)
    for m in re.finditer(pat, text):
        b, e = m.span()
        if any(taken[b:e]):
            continue
        for i in range(b, e):
            taken[i] = True
        spans.append((b, e))
    return spans

def detect_entities(text: str) -> List[Entity]:
    """
    AI 탐지 결과(entities: [{type, value}...])를
    기존 스키마(Entity(value, begin, end, label))로 변환.
    """
    ents: List[Entity] = []
    if not text:
        return ents

    try:
        res = analyze_text(text)  # {"has_sensitive": bool, "entities": [{type, value}, ...]}
    except Exception:
        # AI 실패 시 안전 폴백: 빈 결과
        return ents

    raw_entities = res.get("entities", []) if isinstance(res, dict) else []
    if not isinstance(raw_entities, list):
        return ents

    # 비겹침 스팬으로 begin/end 복원
    for item in raw_entities:
        t = str(item.get("type", "")).strip().upper() if isinstance(item, dict) else ""
        v = str(item.get("value", "")).strip() if isinstance(item, dict) else ""
        if not (t and v):
            continue

        spans = _non_overlapping_spans_by_value(text, v)
        # 값이 원문에 없을 수도 있으므로(전처리·공백 차이 등) 그런 경우는 스킵
        for (b, e) in spans or []:
            ents.append(Entity(value=text[b:e], begin=b, end=e, label=t))

    # 위치순 정렬(겹침은 위 로직에서 방지)
    ents.sort(key=lambda e: (e.begin, -e.end))
    return ents

def has_sensitive_any(prompt_entities: List[Entity], ocr_entities: List[Entity]) -> bool:
    # 하나라도 엔티티가 있으면 민감정보 포함으로 처리
    return bool(prompt_entities or ocr_entities)
