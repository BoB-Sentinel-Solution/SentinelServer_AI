# services/ai_detector.py
# 오프라인 전용 AI 탐지기(모델 1회 로드 → 재사용)

import os, json, threading
from typing import Dict, Any, List, Tuple
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# 오프라인 강제
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

SYS_PROMPT = """
    You are a strict whitelist-only detector for sensitive entities.

    Return ONLY a compact JSON with these keys:
    - has_sensitive: true or false
    - entities: list of {"type": <LABEL>, "value": <exact substring>}

    HARD RULES
    - Allowed labels ONLY (uppercase, exact match). If a label is not in the list below, DO NOT invent or output it.
    - If the text contains none of the allowed entities: return exactly {"has_sensitive": false, "entities": []}.
    - `value` must be the exact substring from the user text (no masking, no redaction, no normalization).
    - Output JSON only — no explanations, no extra text, no code fences, no trailing commas.
    - The JSON must be valid and parseable.

    ALLOWED LABELS
    # 1) Basic Identity Information
    NAME, PHONE, EMAIL, ADDRESS, POSTAL_CODE,
  
    # 2) Public Identification Number
    PERSONAL_CUSTOMS_ID, RESIDENT_ID, PASSPORT, DRIVER_LICENSE, FOREIGNER_ID, HEALTH_INSURANCE_ID, BUSINESS_ID, MILITARY_ID,

    # 3) Authentication Information
    JWT, API_KEY, GITHUB_PAT, PRIVATE_KEY,

    # 4) Finanacial Information
    CARD_NUMBER, CARD_EXPIRY, BANK_ACCOUNT, CARD_CVV, PAYMENT_PIN, MOBILE_PAYMENT_PIN,

    # 5) Cryptocurrency Information
    MNEMONIC, CRYPTO_PRIVATE_KEY, HD_WALLET, PAYMENT_URI_QR, 

    # 6) Network Information + etc
    IPV4, IPV6, MAC_ADDRESS, IMEI
""".strip()


def _extract_json(s: str) -> Dict[str, Any]:
    # 아주 간단한 마지막 { ... } 블록 복구
    end = s.rfind("}")
    if end == -1:
        return {"has_sensitive": False, "entities": []}
    level = 0
    start = None
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
                    start = i
                    break
    if start is None:
        return {"has_sensitive": False, "entities": []}
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return {"has_sensitive": False, "entities": []}


class _Detector:
    def __init__(self, model_dir: str, max_new_tokens: int = 256):
        self.model_dir = model_dir
        self.max_new_tokens = max_new_tokens
        self.tok = AutoTokenizer.from_pretrained(
            model_dir, use_fast=True, local_files_only=True, trust_remote_code=True
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, device_map="auto", torch_dtype="auto",
            local_files_only=True, trust_remote_code=True
        )
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.lock = threading.Lock()

    def analyze(self, text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": text or ""},
        ]
        with self.lock:
            inputs = self.tok.apply_chat_template(
                messages, return_tensors="pt", add_generation_prompt=True
            ).to(self.model.device)
            with torch.no_grad():
                out = self.model.generate(
                    inputs=inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                    eos_token_id=self.tok.eos_token_id,
                )
            decoded = self.tok.decode(out[0], skip_special_tokens=True)
        parsed = _extract_json(decoded)
        if not isinstance(parsed, dict) or \
           "has_sensitive" not in parsed or "entities" not in parsed:
            return {"has_sensitive": False, "entities": []}
        # 방어: 라벨/값 타입만 보정
        ents = []
        try:
            for e in parsed.get("entities", []):
                t = str(e.get("type", "")).strip().upper()
                v = str(e.get("value", "")).strip()
                if t and v:
                    ents.append({"type": t, "value": v})
        except Exception:
            ents = []
        return {"has_sensitive": bool(parsed.get("has_sensitive", False)), "entities": ents}


# ---- 글로벌 싱글톤 핸들(스타트업에서 초기화)
_detector_singleton: _Detector | None = None

def init_from_env() -> None:
    global _detector_singleton
    if _detector_singleton is not None:
        return
    model_dir = os.getenv("MODEL_DIR", "").strip()
    if not model_dir:
        raise RuntimeError("MODEL_DIR env not set")
    max_new = int(os.getenv("MAX_NEW_TOKENS", "256"))
    _detector_singleton = _Detector(model_dir=model_dir, max_new_tokens=max_new)

def analyze_text(text: str) -> Dict[str, Any]:
    if _detector_singleton is None:
        init_from_env()
    return _detector_singleton.analyze(text)
