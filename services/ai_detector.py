# services/ai_detector.py
# 오프라인 전용 AI 탐지기 (모델 1회 로드 → 스레드 세이프 재사용)

from __future__ import annotations

import os
import json
import threading
from typing import Any, Dict, List

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# --- 오프라인/캐시 환경 강제(유닛에서도 설정하지만 여기서도 기본값 보강) ---
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# v5 경고 대응(선택): 유닛에서 HF_HOME 지정하지 않았다면 기본 위치 보강
os.environ.setdefault("HF_HOME", "/var/cache/sentinel/hf")

SYS_PROMPT = """
You are a strict whitelist-only detector for sensitive entities.

Return ONLY a compact JSON with these keys:
- has_sensitive: true or false
- entities: list of {"type": <LABEL>, "value": <exact substring>}

HARD RULES
- Allowed labels ONLY (uppercase, exact match). If a label is not in the list below, DO NOT invent or output it.
- If the text contains none of the allowed entities: return exactly {"has_sensitive": false, "entities": []}.
- `value` must be the exact substring from the user text (no masking, no normalization).
- Output JSON only — no explanations, no extra text, no code fences.

ALLOWED LABELS
# 1) Basic Identity Information
NAME, PHONE, EMAIL, ADDRESS, POSTAL_CODE,

# 2) Public Identification Number
PERSONAL_CUSTOMS_ID, RESIDENT_ID, PASSPORT, DRIVER_LICENSE, FOREIGNER_ID, HEALTH_INSURANCE_ID, BUSINESS_ID, MILITARY_ID,

# 3) Authentication Information
JWT, API_KEY, GITHUB_PAT, PRIVATE_KEY,

# 4) Financial Information
CARD_NUMBER, CARD_EXPIRY, BANK_ACCOUNT, CARD_CVV, PAYMENT_PIN, MOBILE_PAYMENT_PIN,

# 5) Cryptocurrency Information
MNEMONIC, CRYPTO_PRIVATE_KEY, HD_WALLET, PAYMENT_URI_QR,

# 6) Network Information + etc
IPV4, IPV6, MAC_ADDRESS, IMEI
""".strip()

_ALLOWED = {
    "NAME", "PHONE", "EMAIL", "ADDRESS", "POSTAL_CODE",
    "PERSONAL_CUSTOMS_ID", "RESIDENT_ID", "PASSPORT", "DRIVER_LICENSE", "FOREIGNER_ID", "HEALTH_INSURANCE_ID", "BUSINESS_ID", "MILITARY_ID",
    "JWT", "API_KEY", "GITHUB_PAT", "PRIVATE_KEY",
    "CARD_NUMBER", "CARD_EXPIRY", "BANK_ACCOUNT", "CARD_CVV", "PAYMENT_PIN", "MOBILE_PAYMENT_PIN",
    "MNEMONIC", "CRYPTO_PRIVATE_KEY", "HD_WALLET", "PAYMENT_URI_QR",
    "IPV4", "IPV6", "MAC_ADDRESS", "IMEI",
}

def _default_result() -> Dict[str, Any]:
    return {"has_sensitive": False, "entities": []}

def _extract_json(s: str) -> Dict[str, Any]:
    """
    모델이 토크나이저 템플릿까지 함께 디코딩하는 상황을 고려해
    마지막 { ... } 블록을 역방향으로 복구하여 JSON만 파싱.
    """
    end = s.rfind("}")
    if end == -1:
        return _default_result()
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
        return _default_result()
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return _default_result()


class _Detector:
    def __init__(self, model_dir: str, max_new_tokens: int = 256):
        # 로컬 전용 로딩(네트워크 미접속)
        self.tok = AutoTokenizer.from_pretrained(
            model_dir, use_fast=True, local_files_only=True, trust_remote_code=True
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, device_map="auto", torch_dtype="auto",
            local_files_only=True, trust_remote_code=True
        )
        self.model.eval()

        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token

        self.max_new_tokens = max_new_tokens
        self.lock = threading.Lock()

    def analyze(self, text: str) -> Dict[str, Any]:
        """
        입력 텍스트 -> 모델 생성 -> JSON 파싱 -> 허용 라벨만 필터링
        실패 시 안전 폴백(_default_result) 반환.
        """
        messages = [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user",   "content": text or ""},
        ]

        try:
            with self.lock, torch.inference_mode():
                inputs = self.tok.apply_chat_template(
                    messages, return_tensors="pt", add_generation_prompt=True
                ).to(self.model.device)

                out = self.model.generate(
                    inputs=inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                    eos_token_id=self.tok.eos_token_id,
                )

                decoded = self.tok.decode(out[0], skip_special_tokens=True)

            parsed = _extract_json(decoded)
            if not isinstance(parsed, dict):
                return _default_result()

            # has_sensitive 보정
            has_sensitive = bool(parsed.get("has_sensitive", False))

            # 엔티티 필터링(허용 라벨만, 값 공백 제거)
            ents_out: List[Dict[str, str]] = []
            raw_ents = parsed.get("entities") or []
            for e in raw_ents:
                t = str(e.get("type", "")).strip().upper()
                v = str(e.get("value", "")).strip()
                if not t or not v:
                    continue
                if t not in _ALLOWED:
                    continue
                ents_out.append({"type": t, "value": v})
                # 과도한 엔티티 폭주 방지(안전 상한)
                if len(ents_out) >= 128:
                    break

            # 모델이 has_sensitive=False인데 실제 엔티티가 있으면 true로 승격
            if ents_out and not has_sensitive:
                has_sensitive = True

            return {"has_sensitive": has_sensitive, "entities": ents_out}

        except Exception:
            # 어떤 에러도 500으로 번지지 않도록 폴백
            return _default_result()


# ---- 글로벌 싱글톤 핸들(서버 부팅 시 1회 초기화)
_detector_singleton: _Detector | None = None

def init_from_env() -> None:
    """
    환경변수:
      - MODEL_DIR: 로컬 모델 디렉터리 (필수)
      - MAX_NEW_TOKENS: 생성 토큰 수 (기본 256)
    """
    global _detector_singleton
    if _detector_singleton is not None:
        return

    model_dir = os.getenv("MODEL_DIR", "").strip()
    if not model_dir:
        raise RuntimeError("MODEL_DIR env not set")

    max_new = int(os.getenv("MAX_NEW_TOKENS", "256"))
    _detector_singleton = _Detector(model_dir=model_dir, max_new_tokens=max_new)

def analyze_text(text: str) -> Dict[str, Any]:
    """
    외부에서 호출하는 진입점.
    """
    if _detector_singleton is None:
        init_from_env()
    return _detector_singleton.analyze(text)
