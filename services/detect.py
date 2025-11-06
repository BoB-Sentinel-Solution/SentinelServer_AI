# services/detect.py
from __future__ import annotations

import time
from typing import Dict, Any, List, Tuple

from services.ai_detector import analyze_text  # -> {"has_sensitive": bool, "entities": [{"type","value"}]}
# 주의: ai_detector 쪽에서 threading import 되어 있어야 합니다.

def _find_spans(text: str, values: List[str]) -> List[Tuple[int, int, str]]:
    """
    text에서 values 각각의 '첫 번째' 등장 위치(begin,end)를 순차적으로 매칭.
    중복/겹침 최소화를 위해 탐색 시작 오프셋을 앞으로 밀면서 찾음.
    값이 없거나 미발견 시 (-1, -1) 반환 -> 호출부에서 필터링.
    """
    spans: List[Tuple[int, int, str]] = []
    if not text:
        return spans

    start = 0
    lower_text = text  # 한글/대소문자 섞여서 그대로 검색(정확 매칭)

    for v in values:
        if not v:
            spans.append((-1, -1, v))
            continue
        idx = lower_text.find(v, start)
        if idx == -1:
            # 못 찾으면 전체에서 1회 재시도(중복 값/앞쪽에 있을 수 있음)
            idx = lower_text.find(v)
        if idx == -1:
            spans.append((-1, -1, v))
            continue
        begin = idx
        end = idx + len(v)
        spans.append((begin, end, v))
        # 겹치지 않도록 다음 탐색 시작 오프셋 업데이트
        start = end
    return spans


def analyze_with_entities(text: str) -> Dict[str, Any]:
    """
    옵션 A: AI 감지기 결과(type,value) -> 서버 스키마(value, begin, end, label)로 변환.
    실패 시 안전 폴백 반환.
    반환:
      {
        "has_sensitive": bool,
        "entities": [{"value","begin","end","label"}, ...],
        "processing_ms": int
      }
    """
    t0 = time.perf_counter()
    try:
        raw = analyze_text(text or "")
        # 기대 포맷: {"has_sensitive": bool, "entities": [{"type":LABEL, "value":VALUE}, ...]}
        has_sens = bool(raw.get("has_sensitive", False))
        raw_ents = raw.get("entities") or []

        # 값 리스트만 먼저 추출하여 위치 찾기
        values: List[str] = []
        labels: List[str] = []
        for e in raw_ents:
            typ = str(e.get("type", "")).strip().upper()
            val = str(e.get("value", "")).strip()
            if not typ or not val:
                continue
            labels.append(typ)
            values.append(val)

        spans = _find_spans(text or "", values)

        entities: List[Dict[str, Any]] = []
        for (begin, end, val), lab in zip(spans, labels):
            if begin >= 0 and end >= 0:
                entities.append({
                    "value": val,
                    "begin": begin,
                    "end": end,
                    "label": lab,
                })

        ms = int((time.perf_counter() - t0) * 1000)
        return {
            "has_sensitive": has_sens or bool(entities),
            "entities": entities,
            "processing_ms": ms,
        }
    except Exception:
        # 어떤 이유로든 실패하면 안전 폴백
        ms = int((time.perf_counter() - t0) * 1000)
        return {"has_sensitive": False, "entities": [], "processing_ms": ms}
