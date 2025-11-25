# -*- coding: utf-8 -*-
# ai_external.py
from __future__ import annotations
import os, json, shlex, re
from typing import Any, Dict, List, Optional, Tuple
import subprocess  # nosec B404  # shell=False + 인자리스트만 사용(검증된 입력)
import time

# Sentinel 내부 모듈 (로컬 LLM 추론용)
from services import offline_sensitive_detector_min as det_min

# ---- JSON 추출 유틸 (stdout에 경고/로그가 섞여도 OK) ----
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

def _sanitize(s: str) -> str:
    return (
        s.replace("\u2028", "\n")
         .replace("\u2029", "\n")
         .replace("\ufeff", "")
         .strip()
    )

def _find_codefence_json(s: str) -> List[str]:
    return [m.group(1).strip() for m in _CODE_FENCE_RE.finditer(s)]

def _find_all_top_level_json(s: str) -> List[str]:
    blocks: List[str] = []
    level = 0
    in_str = False
    esc = False
    start = None
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                if level == 0:
                    start = i
                level += 1
            elif ch == "}":
                level -= 1
                if level == 0 and start is not None:
                    blocks.append(s[start:i+1].strip())
                    start = None
    return blocks

def _find_last_json(s: str) -> Optional[str]:
    s = _sanitize(s)
    cf = _find_codefence_json(s)
    if cf:
        return cf[-1]
    blocks = _find_all_top_level_json(s)
    if blocks:
        return blocks[-1]
    # 역방향 복구 (마지막 '}'부터)
    end = s.rfind("}")
    if end == -1:
        return None
    level = 0
    in_str = False
    esc = False
    for i in range(end, -1, -1):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "}":
                level += 1
            elif ch == "{":
                level -= 1
                if level == 0:
                    return s[i:end+1].strip()
    return None

# ---- 엔티티 스팬 매핑 (왼→오 순서로 값 소비) ----
def _add_spans(text: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cursor = 0
    for e in entities:
        v = e.get("value") or ""
        if not isinstance(v, str) or not v:
            continue
        idx = text.find(v, cursor)
        if idx < 0:
            idx = text.find(v, 0)
            if idx < 0:
                out.append(dict(e))  # 스팬 없이 통과
                continue
        begin = idx
        end = idx + len(v)
        cursor = end
        e2 = dict(e)
        e2["begin"] = begin
        e2["end"] = end
        out.append(e2)
    return out


# ---- 전역 모델 캐시 ----
_GLOBAL: Dict[str, Any] = {
    "model_dir": None,
    "tok": None,
    "model": None,
}

def _ensure_model_loaded(model_dir: str) -> Tuple[Any, Any]:
    """
    offline_sensitive_detector_min.py 내부와 동일하게
    AutoTokenizer / AutoModelForCausalLM 을 로딩하되,
    프로세스 내에서 한 번만 로드해서 재사용.
    """
    global _GLOBAL

    if (
        _GLOBAL.get("model_dir") == model_dir
        and _GLOBAL.get("tok") is not None
        and _GLOBAL.get("model") is not None
    ):
        return _GLOBAL["tok"], _GLOBAL["model"]

    # offline_sensitive_detector_min 에서 이미 import 한 것들을 재사용
    AutoTokenizer = det_min.AutoTokenizer
    AutoModelForCausalLM = det_min.AutoModelForCausalLM
    torch = det_min.torch

    tok = AutoTokenizer.from_pretrained(
        model_dir,
        trust_remote_code=True,
        local_files_only=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        device_map="auto",
        torch_dtype="auto",
        local_files_only=True,
        trust_remote_code=True,
    )
    model.eval()
    torch.set_grad_enabled(False)

    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    _GLOBAL = {
        "model_dir": model_dir,
        "tok": tok,
        "model": model,
    }
    return tok, model


# ---- 서브프로세스 실행기 → 로컬 모델 실행기로 변경 ----
class OfflineDetectorRunner:
    def __init__(
        self,
        script_path: str = os.path.join(os.path.dirname(__file__), "offline_sensitive_detector_min.py"),
        model_dir: Optional[str] = None,
        max_new_tokens: int = 256,
        timeout_sec: float = 20.0,
        python_bin: str = "python3",
    ):
        self.script_path = script_path
        self.model_dir = model_dir or os.environ.get("MODEL_DIR", "")
        self.max_new_tokens = int(os.environ.get("MAX_NEW_TOKENS", max_new_tokens))
        self.timeout_sec = timeout_sec
        self.python_bin = python_bin
        if not self.model_dir:
            raise RuntimeError("MODEL_DIR is not set (env or constructor).")

    def analyze_text(self, text: str, return_spans: bool = True) -> Dict[str, Any]:
        """
        offline_sensitive_detector_min.run_infer 를 직접 호출하여
        {"has_sensitive": bool, "entities":[{"type","value"(, begin,end)}]} 형태로 반환.
        실패 시 안전 폴백.
        """
        t0 = time.perf_counter()

        try:
            tok, model = _ensure_model_loaded(self.model_dir)
        except Exception:
            return {"has_sensitive": False, "entities": [], "error": "model_load_fail"}

        try:
            # offline_sensitive_detector_min 안의 로직을 그대로 재사용
            parsed = det_min.run_infer(
                tok,
                model,
                text,
                max_new_tokens=int(self.max_new_tokens),
            )
        except Exception:
            return {"has_sensitive": False, "entities": [], "error": "infer_fail"}

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        # 최소 스키마 정리 (기존 로직 유지)
        has = bool(parsed.get("has_sensitive"))
        ents = parsed.get("entities") or []

        clean: List[Dict[str, Any]] = []
        for e in ents:
            if not isinstance(e, dict):
                continue
            t = e.get("type"); v = e.get("value")
            if isinstance(t, str) and isinstance(v, str):
                t = t.strip().upper()
                v = v.strip()
                if t and v:
                    clean.append({"type": t, "value": v})

        if return_spans and clean:
            clean = _add_spans(text, clean)

        return {
            "has_sensitive": bool(clean) if has or clean else False,
            "entities": clean,
            "processing_ms": elapsed_ms,
        }
