# server/app.py
# -*- coding: utf-8 -*-
"""
Sentinel Solution · Inspector Server
- /inspect : 프록시(에이전트)가 보낸 요청 JSON을 받아 AI 판별 + 마스킹을 수행하고 allow/mask/block을 반환.
- 기본은 규칙(정규식) 기반. OPENAI_API_KEY가 설정되면 LLM 보조판별을 사용(선택).
"""

import os
import re
import base64
import json
import hashlib
from typing import Optional, List, Any, Dict, Tuple, Union

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# =========================
# 환경 변수 설정
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()  # 선택: 있으면 LLM 보조판별
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")   # 적절한 소형 모델로
ENABLE_LLM = bool(OPENAI_API_KEY) and os.getenv("ENABLE_LLM", "true").lower() == "true"

BLOCK_ON_HIGH_RISK = os.getenv("BLOCK_ON_HIGH_RISK", "true").lower() == "true"
HIGH_RISK_THRESHOLD = int(os.getenv("HIGH_RISK_THRESHOLD", "2"))   # 고위험 규칙 적중 수≥threshold면 block
MAX_MASK_FIELDS = int(os.getenv("MAX_MASK_FIELDS", "5000"))        # JSON 마스킹 시 최대 필드 수(폭탄 방지)

# =========================
# 간단 로그 유틸
# =========================
def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

# =========================
# 룰(정규식) 정의
# =========================
# 카드번호(Luhn), 이메일, 한국 휴대폰, JWT, AWS Access Key
CARD = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
EMAIL = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b')
PHONE = re.compile(r'\b01[0-9]-?\d{3,4}-?\d{4}\b')
JWT = re.compile(r'\beyJ[\w-]+\.[\w-]+\.[\w-]+\b')
AWS = re.compile(r'\bAKIA[0-9A-Z]{16}\b')
# 그 외 흔한 비밀키/쿠키류(간단 스캐너)
BEARER = re.compile(r'\bBearer\s+([A-Za-z0-9._\-]{20,})')
APIKEY = re.compile(r'\b(?i)(api[_-]?key|x-api-key)\b[:=]\s*([A-Za-z0-9._\-]{16,})')

HIGH_RISK_RULES = {"card", "jwt", "aws_key", "bearer", "apikey"}  # 다수 적중 시 차단 고려

def luhn_ok(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    parity = (len(digits) - 2) % 2
    for i, d in enumerate(digits[:-1]):
        y = d * 2 if (i % 2 == parity) else d
        checksum += y - 9 if y > 9 else y
    return (checksum + digits[-1]) % 10 == 0

# =========================
# 텍스트 마스킹
# =========================
def redact_text(t: str, rules_hit: List[str]) -> str:
    def mask_card(m):
        raw = m.group(0)
        if luhn_ok(raw):
            rules_hit.append("card")
            return re.sub(r'\d(?=\d{4}\b)', '*', raw)
        return raw

    # 카드
    t = CARD.sub(mask_card, t)
    # 이메일
    t = EMAIL.sub(lambda m: (rules_hit.append("email") or (m.group(0)[0] + "***@" + m.group(0).split("@")[1])), t)
    # 전화
    t = PHONE.sub(lambda m: (rules_hit.append("phone") or (m.group(0)[:3] + "-****-" + m.group(0)[-4:])), t)
    # JWT
    t = JWT.sub(lambda m: (rules_hit.append("jwt") or (m.group(0)[:4] + "****" + m.group(0)[-4:])), t)
    # AWS Access Key
    t = AWS.sub(lambda m: (rules_hit.append("aws_key") or (m.group(0)[:4] + "****" + m.group(0)[-4:])), t)
    # Bearer 토큰
    t = BEARER.sub(lambda m: (rules_hit.append("bearer") or ("Bearer " + (m.group(1)[:4] + "****" + m.group(1)[-4:]))), t)
    # apikey= / x-api-key:
    def _mask_apikey(m):
        rules_hit.append("apikey")
        key = m.group(2)
        masked = key[:4] + "****" + key[-4:] if len(key) >= 8 else "***"
        return f"{m.group(1)}: {masked}"
    t = APIKEY.sub(_mask_apikey, t)
    return t

# =========================
# JSON 구조 마스킹(깊이 순회)
# =========================
def redact_any(value: Any, rules_hit: List[str], counter: List[int]) -> Any:
    """
    - 문자열: redact_text 적용
    - 리스트/객체: 재귀
    - counter[0] : 처리한 원소 수(상한 넘으면 더 처리 안 함)
    """
    if counter[0] > MAX_MASK_FIELDS:
        return value

    if isinstance(value, str):
        counter[0] += 1
        return redact_text(value, rules_hit)
    elif isinstance(value, list):
        out = []
        for v in value:
            if counter[0] > MAX_MASK_FIELDS:
                out.append(v)
            else:
                out.append(redact_any(v, rules_hit, counter))
        return out
    elif isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if counter[0] > MAX_MASK_FIELDS:
                out[k] = v
            else:
                out[k] = redact_any(v, rules_hit, counter)
        return out
    else:
        return value

def try_json_masking(text: str, rules_hit: List[str]) -> Tuple[Optional[str], bool]:
    """
    가능한 경우 JSON 구조를 유지한 채 마스킹한 뒤 문자열로 재직렬화.
    - 성공 시 (masked_str, True)
    - 실패 시 (None, False) -> 평문 텍스트 마스킹으로 대체
    """
    try:
        obj = json.loads(text)
    except Exception:
        return None, False
    counter = [0]
    masked = redact_any(obj, rules_hit, counter)
    try:
        return json.dumps(masked, ensure_ascii=False), True
    except Exception:
        return None, False

# =========================
# (선택) LLM 보조 판별
# =========================
def llm_judgement(sample_text: str) -> Tuple[str, float]:
    """
    외부 LLM을 사용해 민감도 판별(선택). 반환: (label, confidence)
    label ∈ {"clean", "sensitive"}.
    """
    if not ENABLE_LLM:
        return "clean", 0.0
    try:
        # 외부 호출(예시): OpenAI 공식 SDK
        # pip install openai
        from openai import OpenAI
        cli = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            "You are a strict detector for sensitive data (PII, secrets, access keys). "
            "Return JSON with keys: label (clean|sensitive) and confidence (0..1). "
            "Consider credit cards, JWT/cookies/tokens, API keys, phone/email, bank/account, "
            "cloud secrets (AKIA..), and anything that could authenticate a user or payment. "
            "Text:\n" + sample_text[:4000]
        )
        res = cli.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        txt = res.choices[0].message.content.strip()
        # 간단 파서
        label = "clean"; conf = 0.0
        try:
            j = json.loads(txt)
            label = j.get("label", "clean").lower()
            conf = float(j.get("confidence", 0.0))
        except Exception:
            # 비JSON이면 키워드로 추정
            if "sensitive" in txt.lower():
                label, conf = "sensitive", 0.6
        return label if label in ("clean","sensitive") else "clean", max(0.0, min(conf, 1.0))
    except Exception:
        # LLM 장애 시 보수적으로 clean 취급(규칙 엔진이 주역)
        return "clean", 0.0

# =========================
# FastAPI 스키마/엔드포인트
# =========================
class InspectIn(BaseModel):
    time: str
    interface: str
    direction: str
    method: str
    scheme: str
    host: str
    port: int
    path: str
    query: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    body_b64: Optional[str] = None
    client_ip: Optional[str] = None
    server_ip: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)

class InspectOut(BaseModel):
    decision: str                  # "allow" | "mask" | "block"
    reason: str
    masked_body_b64: Optional[str] = None
    redactions: List[str] = Field(default_factory=list)
    rules_hit: List[str] = Field(default_factory=list)
    ttl_ms: int = 0

app = FastAPI(title="Sentinel Inspector", version="1.0.0")

@app.post("/inspect", response_model=InspectOut)
async def inspect(inp: InspectIn, req: Request):
    # 1) 본문 복원
    body_bytes = b""
    if inp.body_b64:
        try:
            body_bytes = base64.b64decode(inp.body_b64)
        except Exception:
            body_bytes = b""
    body_text = ""
    if body_bytes:
        try:
            body_text = body_bytes.decode("utf-8", errors="ignore")
        except Exception:
            body_text = ""

    # 2) 룰 기반 마스킹
    rules_hit: List[str] = []
    masked_text_json, ok_json = try_json_masking(body_text, rules_hit) if body_text else (None, False)
    if ok_json:
        masked_text = masked_text_json
    else:
        masked_text = redact_text(body_text, rules_hit) if body_text else ""

    # 3) LLM 보조 판별(선택)
    #    - 룰 적중이 적어도, LLM이 민감하다고 판단하면 mask로 격상
    llm_label, llm_conf = llm_judgement(body_text) if body_text else ("clean", 0.0)
    if llm_label == "sensitive" and llm_conf >= 0.6:
        if body_text and not rules_hit:
            rules_hit.append("llm_sensitive")

    # 4) 의사결정
    #    우선순위: 다수 고위험 룰 적중 → block (옵션)
    high_risk_hits = sum(1 for r in rules_hit if r in HIGH_RISK_RULES)
    if BLOCK_ON_HIGH_RISK and high_risk_hits >= HIGH_RISK_THRESHOLD:
        return InspectOut(
            decision="block",
            reason="high_risk_detected",
            masked_body_b64=None,
            redactions=list(sorted(set(rules_hit))),
            rules_hit=rules_hit,
            ttl_ms=0,
        )

    decision = "allow"
    masked_b64 = None
    if rules_hit or (llm_label == "sensitive" and llm_conf >= 0.6):
        decision = "mask"
        if masked_text:
            masked_b64 = base64.b64encode(masked_text.encode("utf-8")).decode()

    # 5) 결과 반환
    reason = "clean" if decision == "allow" else ("pii_or_secret_detected" if decision == "mask" else "blocked")
    return InspectOut(
        decision=decision,
        reason=reason,
        masked_body_b64=masked_b64,
        redactions=list(sorted(set(rules_hit))),
        rules_hit=rules_hit,
        ttl_ms=0,
    )

@app.get("/healthz")
async def health():
    return {"ok": True, "llm_enabled": ENABLE_LLM}
