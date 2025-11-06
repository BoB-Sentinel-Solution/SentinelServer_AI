# services/db_logging.py
from __future__ import annotations

import uuid, time, os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from schemas import InItem, ServerOut, Entity
from models import LogRecord
from services.ocr import OcrService
from services.masking import mask_by_entities, mask_with_parens_by_entities
from services.attachment import save_attachment_file
from services.similarity import best_similarity_against_folder
from repositories.log_repo import LogRepository

# 1) 정규식 1차 감지기
from services.regex_detector import detect_entities as regex_detect
# 2) 외부 판별기 러너(offline_sensitive_detector_min.py 호출)
from services.ai_external import OfflineDetectorRunner

ADMIN_IMAGE_DIR = Path("./SentinelServer_AI/adminset/image")
SIMILARITY_THRESHOLD = 0.4  # 이미지 유사도 차단 임계

# 러너 싱글턴 (MODEL_DIR, MAX_NEW_TOKENS는 .env에서 읽힘)
_DETECTOR = OfflineDetectorRunner(
    model_dir=os.environ.get("MODEL_DIR", "").strip() or None,
    timeout_sec=20.0,
)

def _rebase_ai_entities_on_original(original: str, ai_ents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    AI가 마스킹된 프롬프트에서 잡아낸 {type/value}를
    '원문(original)'에서 다시 찾아 begin/end를 붙여 반환.
    (값이 원문에 없으면 스킵)
    """
    out: List[Dict[str, Any]] = []
    cursor = 0
    for e in ai_ents:
        label = (e.get("type") or e.get("label") or "").strip().upper()
        value = (e.get("value") or "").strip()
        if not label or not value:
            continue
        idx = original.find(value, cursor)
        if idx < 0:
            idx = original.find(value)
            if idx < 0:
                continue
        b, en = idx, idx + len(value)
        cursor = en
        out.append({"label": label, "value": value, "begin": b, "end": en})
    return out

def _dedup_spans(base: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    스팬 중복 제거: base 우선, extra는 같은 라벨에서 겹치면 버림.
    (완전 동일 스팬이거나 라벨 동일 & 구간 겹치면 스킵)
    """
    out = list(base)
    for e in extra:
        eb, ee, el = e["begin"], e["end"], e["label"]
        conflict = False
        for x in out:
            xb, xe, xl = x["begin"], x["end"], x["label"]
            if (eb == xb and ee == xe) or (el == xl and not (ee <= xb or xe <= eb)):
                conflict = True
                break
        if not conflict:
            out.append(e)
    return out

# ---------- alert(근거) 생성 로직 ----------
def _ent_key(e: Dict[str, Any]) -> Tuple[str, int, int]:
    """엔티티를 (label, begin, end) 튜플 키로 식별."""
    return (str(e.get("label", "")).upper(), int(e.get("begin", -1)), int(e.get("end", -1)))

def _build_alert_from_merged(merged_ents: List[Dict[str, Any]],
                             regex_src: List[Dict[str, Any]],
                             ai_src: List[Dict[str, Any]]) -> str:
    """
    최종 병합된 엔티티(= 실제 마스킹/저장에 쓰이는 것) 기준으로,
    각 엔티티의 '출처'를 정규식/AI로 태깅하여 라벨을 소스별로 집계.
    같은 라벨이라도 서로 다른 인스턴스면 각각 소스대로만 집계한다.
    """
    regex_keys = {_ent_key(e) for e in regex_src}
    ai_keys    = {_ent_key(e) for e in ai_src}

    labels_regex: List[str] = []
    labels_ai: List[str] = []

    for e in merged_ents:
        k = _ent_key(e)
        lab = str(e.get("label", "")).upper()
        if k in regex_keys and k in ai_keys:
            # 직렬 파이프라인 특성상 드뭄. 필요 시 한쪽만 집계.
            labels_regex.append(lab)
        elif k in regex_keys:
            labels_regex.append(lab)
        elif k in ai_keys:
            labels_ai.append(lab)
        else:
            # 이 케이스는 거의 없음(병합 대상은 둘 중 하나에서 온 것이니까)
            pass

    only_regex = sorted(set(labels_regex))
    only_ai    = sorted(set(labels_ai))

    parts = []
    if only_regex:
        parts.append(f"{', '.join(only_regex)} 값이 정규식으로 식별되었습니다.")
    if only_ai:
        parts.append(f"{', '.join(only_ai)} 값은 AI로 식별되었습니다.")

    return " ".join(parts)

class DbLoggingService:
    @staticmethod
    def _serialize_attachment(att) -> Dict[str, Any] | None:
        if att is None:
            return None
        if hasattr(att, "model_dump"):
            return att.model_dump()
        if hasattr(att, "dict"):
            return att.dict()
        return None

    @staticmethod
    def handle(db: Session, item: InItem) -> ServerOut:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())

        # 1) 첨부 저장
        saved_info = save_attachment_file(item)  # -> (path, mime) or None
        saved_path: Optional[Path] = None
        saved_mime: Optional[str] = None
        if saved_info:
            saved_path, saved_mime = saved_info

        # 2) OCR
        ocr_text, ocr_used, _ = OcrService.run_ocr(item)

        # 3) 정규식 1차 감지 (원문 기준 스팬 확보)
        prompt_text = item.prompt or ""
        try:
            regex_ents_prompt: List[Dict[str, Any]] = regex_detect(prompt_text)  # [{label,value,begin,end}, ...]
        except Exception:
            regex_ents_prompt = []

        # 4) AI 입력용 마스킹(정규식 결과로만 라벨링, 괄호 포함)
        masked_for_ai = mask_with_parens_by_entities(
            prompt_text,
            [Entity(**e) for e in regex_ents_prompt if set(e).issuperset({"label","value","begin","end"})]
        )

        # (선택) OCR 텍스트에도 정규식 적용 (민감도 판정에는 반영하지만, 표시/저장은 프롬프트만)
        if ocr_used and ocr_text:
            try:
                regex_ents_ocr = regex_detect(ocr_text)
            except Exception:
                regex_ents_ocr = []
        else:
            regex_ents_ocr = []

        # 5) AI 보완 탐지 — 힌트 라벨 없이, 마스킹된 프롬프트만 전달
        #    기대 출력: {"has_sensitive": bool, "entities":[{"type","value"}], "processing_ms": <int?>}
        try:
            det_ai = _DETECTOR.analyze_text(masked_for_ai, return_spans=False)
        except Exception:
            det_ai = {"has_sensitive": False, "entities": [], "processing_ms": 0}

        ai_raw_ents = det_ai.get("entities", []) or []
        ai_ms = int(det_ai.get("processing_ms", 0) or 0)

        # 6) AI 결과를 원문 기준 스팬으로 재계산 → 정규식 결과와 병합
        ai_ents_rebased = _rebase_ai_entities_on_original(prompt_text, ai_raw_ents)
        prompt_entities = _dedup_spans(regex_ents_prompt, ai_ents_rebased)

        # OCR에서 정규식으로 잡힌 것들도 민감도 판정에 반영(표시는 프롬프트만)
        has_sensitive = bool(prompt_entities or regex_ents_ocr or bool(det_ai.get("has_sensitive")))

        # 7) 정책결정 (이미지 유사도 포함)
        file_blocked = False
        allow = True
        action = "mask_and_allow" if prompt_entities else "allow"

        if (
            saved_mime
            and saved_mime.startswith("image/")
            and ocr_used
            and (not ocr_text or len(ocr_text.strip()) < 3)
        ):
            try:
                if saved_path and ADMIN_IMAGE_DIR.exists():
                    score, _ = best_similarity_against_folder(saved_path, ADMIN_IMAGE_DIR)
                    if score >= SIMILARITY_THRESHOLD:
                        file_blocked = True
                        allow = False
                        action = "block_upload_similar"
            except Exception:
                pass

        # 8) 최종 마스킹(정규식 + AI 보완 엔티티 모두 반영, 괄호 없음)
        final_modified_prompt = mask_by_entities(
            prompt_text,
            [Entity(**e) for e in prompt_entities if set(e).issuperset({"label","value","begin","end"})]
        )

        # 9) alert(근거) 생성 — 최종 병합 결과 기준으로 출처 집계
        alert_text = _build_alert_from_merged(
            merged_ents=prompt_entities,
            regex_src=regex_ents_prompt,
            ai_src=ai_ents_rebased,
        )
        if not alert_text and prompt_entities:
            # 안전망: 최종 라벨만이라도 노출
            labels = sorted({e["label"] for e in prompt_entities})
            if labels:
                alert_text = f"Detected: {', '.join(labels)}"

        # 전체 처리시간 (AI 처리시간도 포함해 최소값 보정)
        processing_ms = max(int((time.perf_counter() - t0) * 1000), ai_ms)

        # hostname 우선, 없으면 pc_name 대체 (schemas가 별칭 처리)
        host_name = item.hostname or item.pc_name

        # 10) DB 저장 (프롬프트 엔티티만 저장)
        rec = LogRecord(
            request_id      = request_id,
            time            = item.time,
            public_ip       = item.public_ip,
            private_ip      = item.private_ip,
            host            = item.host or "unknown",
            hostname        = host_name,  # 컬럼명: hostname
            prompt          = prompt_text,
            attachment      = DbLoggingService._serialize_attachment(item.attachment),
            interface       = item.interface or "llm",

            modified_prompt = final_modified_prompt,
            has_sensitive   = has_sensitive,
            entities        = [dict(e) for e in prompt_entities],
            processing_ms   = processing_ms,

            file_blocked    = file_blocked,
            allow           = allow,
            action          = action,
        )
        LogRepository.create(db, rec)

        # 11) 응답 (에이전트로 '근거' 전달)
        return ServerOut(
            request_id      = request_id,
            host            = rec.host,
            modified_prompt = rec.modified_prompt,
            has_sensitive   = rec.has_sensitive,
            entities        = [
                Entity(**e) for e in rec.entities
                if isinstance(e, dict) and set(e).issuperset({"value","begin","end","label"})
            ],
            processing_ms   = rec.processing_ms,
            file_blocked    = rec.file_blocked,
            allow           = rec.allow,
            action          = rec.action,
            alert           = alert_text,
        )
