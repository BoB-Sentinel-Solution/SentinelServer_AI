# services/reason_llm.py
from __future__ import annotations
import os, json
from typing import List, Dict, Any, Tuple

from models import LogRecord
from services.ai_external import _ensure_model_loaded
from services import offline_sensitive_detector_min as det_min

# .env 에서 그대로 가져옴 (없으면 기본값)
MODEL_DIR = os.environ.get("MODEL_DIR", "/root/runs/qwen4b_sft_merged2")
MAX_NEW_TOKENS = int(os.environ.get("REASON_MAX_NEW_TOKENS", "256"))

# Reason 전용 시스템 프롬프트
REASON_SYS_PROMPT = """
You are a security analyst specializing in insider data leakage.

Given:
- A sequence of up to 6 LLM prompts from the SAME user (same host + PC).
- The last prompt is the CURRENT one where sensitive data was detected.
- For each prompt, you see: time, host, PC name, public/private IP, and the prompt text.
- You also see which sensitive entity labels were detected in the CURRENT prompt.

Your task:
1) Decide if the CURRENT prompt looks like:
   - "intentional": deliberate attempt to exfiltrate or test the system with real sensitive data
   - "negligent": user carelessness, copy-paste mistake, or misunderstanding of policy
   - "unknown": cannot judge from context

2) Briefly explain WHY in one short sentence (<= 80 characters, Korean).

Return ONLY a compact JSON with:
{
  "intent_type": "intentional" | "negligent" | "unknown",
  "reason": "<짧은 한국어 한 줄 설명>"
}

Rules:
- If there is repeated similar sensitive data or clearly malicious phrasing → prefer "intentional".
- If the user seems to paste existing documents, screenshots, or test samples by mistake → "negligent".
- If context is ambiguous or too short → "unknown".
- Output valid JSON only. No extra text, no code fences.
""".strip()


def _build_reason_prompt(context_logs: List[LogRecord], risk_info: Dict[str, Any]) -> str:
    """
    context_logs: 이전 5개 + 현재 로그 (최대 6개, time 오름차순 가정)
    risk_info: classify_risk_from_entities() 결과
    """
    lines: List[str] = []
    lines.append(REASON_SYS_PROMPT)
    lines.append("")
    lines.append("=== CONTEXT LOGS ===")

    for i, r in enumerate(context_logs):
        idx = i + 1
        t = r.created_at.isoformat() if getattr(r, "created_at", None) else ""
        host = r.host or ""
        pc = r.hostname or ""
        pub = r.public_ip or ""
        priv = r.private_ip or ""
        prompt = (r.prompt or "").replace("\n", " ").strip()
        if len(prompt) > 200:
            prompt = prompt[:200] + "…"

        lines.append(
            f"[{idx}] time={t} host={host} pc={pc} pub={pub} priv={priv}"
        )
        lines.append(f"    prompt: {prompt}")

    lines.append("")
    lines.append("=== CURRENT PROMPT RISK INFO ===")
    lines.append(f"category: {risk_info.get('category', '')}")
    lines.append(f"pattern: {risk_info.get('pattern', '')}")
    lines.append(f"description: {risk_info.get('description', '')}")
    lines.append("")
    lines.append("Now respond with the JSON described above.")

    return "\n".join(lines)


def _run_llm(prompt: str) -> Dict[str, Any]:
    """
    공통 LLM 호출 로직:
    - ai_external._ensure_model_loaded() 로 탐지 모델과 같은 인스턴스를 재사용
    - offline_sensitive_detector_min.extract_best_json() 재사용
    """
    if not MODEL_DIR:
        return {"intent_type": "unknown", "reason": "MODEL_DIR가 설정되지 않았습니다."}

    tok, model = _ensure_model_loaded(MODEL_DIR)

    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with det_min.torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            eos_token_id=tok.eos_token_id,
        )

    full_text = tok.decode(out[0], skip_special_tokens=True)
    json_candidate = det_min.extract_best_json(full_text)
    if not json_candidate:
        return {"intent_type": "unknown", "reason": "LLM JSON 응답 파싱 실패"}

    try:
        parsed = json.loads(json_candidate)
        if not isinstance(parsed, dict):
            raise ValueError("not dict")
        it = parsed.get("intent_type")
        rs = parsed.get("reason")
        if it not in ("intentional", "negligent", "unknown"):
            it = "unknown"
        if not isinstance(rs, str) or not rs.strip():
            rs = "LLM 판단 결과를 해석할 수 없습니다."
        return {"intent_type": it, "reason": rs.strip()}
    except Exception:
        return {"intent_type": "unknown", "reason": "LLM JSON 응답 파싱 실패"}


def infer_intent_with_llm(
    context_logs: List[LogRecord],
    risk_info: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Reason API에서 사용할 진입점.
    return: (intent_type, reason_text)
    """
    if not context_logs:
        return "unknown", "컨텍스트 로그가 부족하여 의도성을 판단하기 어렵습니다."

    prompt = _build_reason_prompt(context_logs, risk_info)
    out = _run_llm(prompt)
    return out.get("intent_type", "unknown"), out.get("reason", "")
