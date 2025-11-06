# services/detect.py
from __future__ import annotations
import time, os
from typing import Dict, Any, List, Tuple
from services.ai_external import OfflineDetectorRunner  # 외부 실행기

# 싱글턴 러너(.env의 MODEL_DIR/MAX_NEW_TOKENS 사용)
_DETECTOR = OfflineDetectorRunner(
    model_dir=os.environ.get("MODEL_DIR", "").strip() or None,
    timeout_sec=20.0,
)

def _find_spans(text: str, values: List[str]) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    if not text:
        return spans
    start = 0
    lower_text = text
    for v in values:
        if not v:
            spans.append((-1, -1, v)); continue
        idx = lower_text.find(v, start)
        if idx == -1:
            idx = lower_text.find(v)
        if idx == -1:
            spans.append((-1, -1, v)); continue
        begin, end = idx, idx + len(v)
        spans.append((begin, end, v))
        start = end
    return spans

def analyze_with_entities(text: str) -> Dict[str, Any]:
    """
    외부 판별기 결과(type,value[,begin,end])를
    서버 스키마(value, begin, end, label)로 변환해 반환.
    """
    t0 = time.perf_counter()
    try:
        # 외부 실행기 호출 (스팬 포함)
        res = _DETECTOR.analyze_text(text or "", return_spans=True)
        raw_ents = res.get("entities") or []

        # begin/end가 이미 있으면 그대로, 없으면 여기서 복구
        values: List[str] = []
        labels: List[str] = []
        entities: List[Dict[str, Any]] = []
        need_spans_fix = False

        for e in raw_ents:
            lab = str(e.get("type") or e.get("label") or "").strip().upper()
            val = str(e.get("value") or "").strip()
            if not lab or not val:
                continue
            if isinstance(e.get("begin"), int) and isinstance(e.get("end"), int):
                entities.append({"value": val, "begin": e["begin"], "end": e["end"], "label": lab})
            else:
                labels.append(lab); values.append(val); need_spans_fix = True

        if need_spans_fix and values:
            spans = _find_spans(text or "", values)
            for (begin, end, val), lab in zip(spans, labels):
                if begin >= 0 and end >= 0:
                    entities.append({"value": val, "begin": begin, "end": end, "label": lab})

        ms = int((time.perf_counter() - t0) * 1000)
        has_sensitive = bool(res.get("has_sensitive") or entities)
        return {"has_sensitive": has_sensitive, "entities": entities, "processing_ms": ms}
    except Exception:
        ms = int((time.perf_counter() - t0) * 1000)
        return {"has_sensitive": False, "entities": [], "processing_ms": ms}
