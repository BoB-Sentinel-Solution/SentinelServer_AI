# -*- coding: utf-8 -*-
# ai_external.py
from __future__ import annotations
import os, json, shlex, re
from typing import Any, Dict, List, Optional, Tuple
import subprocess  # nosec B404  # shell=False + 인자리스트만 사용(검증된 입력)

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

# ---- 서브프로세스 실행기 ----
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
        offline_sensitive_detector_min.py 를 --text 로 호출하여
        {"has_sensitive": bool, "entities":[{"type","value"(, begin,end)}]} 형태로 반환.
        실패 시 안전 폴백.
        """
        # NOTE: Bandit B602 대응 — shell=False + 인자리스트 사용
        args = [
            self.python_bin,
            self.script_path,
            "--model_dir", self.model_dir,
            "--text", text,
            "--max_new_tokens", str(int(self.max_new_tokens)),
        ]

        try:
            proc = subprocess.run(  # nosec B603 (인자리스트+shell=False)
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"has_sensitive": False, "entities": [], "error": "timeout"}

        out = (proc.stdout or "") + ("\n" + (proc.stderr or "") if proc.stderr else "")
        j = _find_last_json(out)
        if not j:
            return {"has_sensitive": False, "entities": [], "error": "no_json"}

        try:
            parsed = json.loads(j)
        except Exception:
            return {"has_sensitive": False, "entities": [], "error": "json_parse_fail"}

        # 최소 스키마 정리
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

        return {"has_sensitive": bool(clean) if has or clean else False, "entities": clean}
