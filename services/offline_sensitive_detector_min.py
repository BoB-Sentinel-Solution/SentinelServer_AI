# offline_sensitive_detector_min.py
# -*- coding: utf-8 -*-
"""
오프라인 전용 민감정보 판별기(간소화 버전)
- 외부 통신 완전 차단(HF/Transformers 오프라인 모드 + local_files_only)
- 모델/토크나이저는 --model_dir 로컬 경로에서만 로드
- 표준출력에는 "파싱된 JSON" 한 줄씩만 출력 (추가 로그/시간 측정 없음)
- 파싱 실패 시 안전 폴백: {"has_sensitive": false, "entities": []}

사용 예시
---------
python offline_sensitive_detector_min.py --model_dir runs/qwen7b_sft_merged --text "연락처 010-1234-5678"
python offline_sensitive_detector_min.py --model_dir runs/qwen7b_sft_merged --input samples.txt --limit 0
"""
import os, sys, json, argparse, re
from typing import Optional, Dict, Any, List

# -------- 오프라인 강제 --------
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ------------------------------- 시스템 프롬프트 -------------------------------
SYS_PROMPT = (
    """
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
    """
    )

# --------- JSON 추출 유틸 ---------
CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

def sanitize_text(s: str) -> str:
    return (s.replace("\u2028", "\n")
             .replace("\u2029", "\n")
             .replace("\ufeff", "")).strip()

def strip_role_headers_shallow(s: str) -> str:
    s = s.lstrip()
    for prefix in ("system\n", "user\n", "assistant\n"):
        if s.startswith(prefix):
            s = s[len(prefix):].lstrip()
    return s

def find_codefence_json_blocks(s: str) -> List[str]:
    return [m.group(1).strip() for m in CODE_FENCE_RE.finditer(s)]

def find_all_top_level_json_blocks(s: str) -> List[str]:
    """문자열 내 최상위 { ... } 블록 '모두' 수집 (문자열/이스케이프 인식)"""
    blocks = []
    first = s.find("{")
    if first == -1:
        return blocks
    level = 0
    in_str = False
    esc = False
    start_idx = None
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
                    start_idx = i
                level += 1
            elif ch == "}":
                level -= 1
                if level == 0 and start_idx is not None:
                    blocks.append(s[start_idx:i+1].strip())
                    start_idx = None
    return blocks

def find_last_top_level_json_backward(s: str) -> Optional[str]:
    """마지막 '}'부터 역방향으로 매칭해 마지막 최상위 JSON 블록을 복원 (백업용)"""
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

def extract_best_json(s: str) -> Optional[str]:
    """
    우선순위:
      (1) 코드펜스 내부의 '마지막' JSON
      (2) 평문 내 최상위 JSON 블록 중 '마지막'
      (3) 마지막 '}' 기준 역방향 스캔 복구
    """
    s = sanitize_text(strip_role_headers_shallow(s))
    cf = find_codefence_json_blocks(s)
    if cf:
        return cf[-1]
    blocks = find_all_top_level_json_blocks(s)
    if blocks:
        return blocks[-1]
    return find_last_top_level_json_backward(s)

# --------- 추론(한 샘플) ---------
def run_infer(tok, model, text: str, max_new_tokens: int = 256) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": text},
    ]
    inputs = tok.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True).to(model.device)
    with torch.no_grad():
        out = model.generate(
            inputs=inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=tok.eos_token_id,
        )
    # 디코드 후, 프롬프트를 제외한 생성 텍스트만 슬라이스
    full_text = tok.decode(out[0], skip_special_tokens=True)
    # chat_template를 쓰면 원문 메시지+assistant 토막이 같이 들어오므로,
    # 마지막 assistant 영역만 남도록 단순히 마지막 '{'부터 복구 파이프라인으로 처리
    json_candidate = extract_best_json(full_text)
    if json_candidate is None:
        return {"has_sensitive": False, "entities": []}
    try:
        parsed = json.loads(json_candidate)
        # 형식 방어 — 필수 키 강제
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
        if "has_sensitive" not in parsed or "entities" not in parsed:
            raise ValueError("missing keys")
        return parsed
    except Exception:
        return {"has_sensitive": False, "entities": []}

# ------------------------------- 메인 -------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_dir", required=True, help="로컬 모델 디렉터리")
    ap.add_argument("--text", type=str, default=None, help="단일 텍스트")
    ap.add_argument("--input", type=str, default=None, help="라인 단위 텍스트 파일")
    ap.add_argument("--limit", type=int, default=0, help="처리할 최대 라인 수(0=전체)")
    ap.add_argument("--max_new_tokens", type=int, default=256)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(
        args.model_dir, use_fast=True, local_files_only=True, trust_remote_code=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir, device_map="auto", torch_dtype="auto", local_files_only=True, trust_remote_code=True
    )
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    samples: List[str] = []
    if args.text:
        samples = [args.text]
    elif args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            samples = [line.strip() for line in f if line.strip()]
    else:
        if not sys.stdin.isatty():
            samples = [line.strip() for line in sys.stdin if line.strip()]
        else:
            print(json.dumps({"has_sensitive": False, "entities": []}, ensure_ascii=False))
            return

    if args.limit and args.limit > 0:
        samples = samples[: args.limit]

    for s in samples:
        result = run_infer(tok, model, s, max_new_tokens=args.max_new_tokens)
        print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
