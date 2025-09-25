import base64
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .schemas import InspectIn, InspectOut
from .masking import redact_text, try_json_masking
from .llm import llm_judgement
from .rules import HIGH_RISK_RULES
from .config import BLOCK_ON_HIGH_RISK, HIGH_RISK_THRESHOLD, ENABLE_HMAC
from .security import verify_hmac

router = APIRouter()

@router.get("/healthz")
async def healthz():
    return {"ok": True, "mtls": True}

@router.post("/inspect", response_model=InspectOut)
async def inspect(inp: InspectIn, request: Request):
    raw = await request.body()
    if ENABLE_HMAC and not verify_hmac(raw, request.headers):
        return JSONResponse(
            {"decision": "block", "reason": "bad_signature", "masked_body_b64": None,
             "redactions": [], "rules_hit": ["sig_fail"], "ttl_ms": 0},
            status_code=200
        )

    body_bytes = base64.b64decode(inp.body_b64) if inp.body_b64 else b""
    body_text = body_bytes.decode("utf-8", errors="ignore") if body_bytes else ""

    rules_hit = []
    masked_text_json, ok_json = try_json_masking(body_text, rules_hit) if body_text else (None, False)
    masked_text = masked_text_json if ok_json else (redact_text(body_text, rules_hit) if body_text else "")

    llm_label, llm_conf = llm_judgement(body_text) if body_text else ("clean", 0.0)
    if llm_label == "sensitive" and llm_conf >= 0.6 and not rules_hit:
        rules_hit.append("llm_sensitive")

    high_risk_hits = sum(1 for r in rules_hit if r in HIGH_RISK_RULES)
    if BLOCK_ON_HIGH_RISK and high_risk_hits >= HIGH_RISK_THRESHOLD:
        return InspectOut(decision="block", reason="high_risk_detected",
                          masked_body_b64=None, redactions=sorted(set(rules_hit)),
                          rules_hit=rules_hit, ttl_ms=0)

    decision = "allow"
    masked_b64 = None
    if rules_hit or (llm_label == "sensitive" and llm_conf >= 0.6):
        decision = "mask"
        if masked_text:
            masked_b64 = base64.b64encode(masked_text.encode("utf-8")).decode()

    reason = "clean" if decision == "allow" else ("pii_or_secret_detected" if decision == "mask" else "blocked")
    return InspectOut(decision=decision, reason=reason, masked_body_b64=masked_b64,
                      redactions=sorted(set(rules_hit)), rules_hit=rules_hit, ttl_ms=0)
