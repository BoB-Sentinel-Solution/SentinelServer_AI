# services/db_logging.py
from __future__ import annotations

import uuid, time, os, base64
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from schemas import InItem, ServerOut, Entity
from models import LogRecord
from services.ocr import OcrService
from services.masking import mask_by_entities, mask_with_parens_by_entities
from services.attachment import save_attachment_file, SavedFileInfo
from services.similarity import best_similarity_against_folder
from repositories.log_repo import LogRepository

# 1) 정규식 1차 감지기
from services.regex_detector import detect_entities as regex_detect
# 2) 외부 판별기 러너(offline_sensitive_detector_min.py 호출)
from services.ai_external import OfflineDetectorRunner

# 3) 파일 처리(문서 detection / 이미지·PDF redaction)
from services.files import process_saved_file, redact_saved_file, DOC_EXTS

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
        """
        DB에 원본 attachment를 그대로 저장할 때 사용.
        """
        if att is None:
            return None
        if hasattr(att, "model_dump"):
            return att.model_dump()
        if hasattr(att, "dict"):
            return att.dict()
        if isinstance(att, dict):
            return dict(att)
        return None

    @staticmethod
    def _get_attachment_format(att) -> Optional[str]:
        """
        InItem.attachment 에서 format 확장자 추출.
        (dict / Pydantic 모델 모두 대응)
        """
        if att is None:
            return None
        fmt = None
        if hasattr(att, "format"):
            fmt = getattr(att, "format", None)
        elif isinstance(att, dict):
            fmt = att.get("format")
        if not fmt:
            return None
        return str(fmt).lower()

    @staticmethod
    def _build_response_attachment(att_src, processed_path: Optional[Path]) -> Dict[str, Any] | None:
        """
        에이전트로 돌려보낼 attachment JSON 생성.
        - format: 들어온 attachment.format 을 그대로 사용 (없으면 파일 확장자)
        - data: 처리된 파일을 base64로 인코딩
        - size: (선택) 처리된 파일 바이트 크기
        """
        if processed_path is None or not processed_path.exists():
            return None

        fmt = DbLoggingService._get_attachment_format(att_src)
        if not fmt:
            fmt = processed_path.suffix.lstrip(".").lower() or "bin"

        try:
            raw = processed_path.read_bytes()
        except Exception:
            return None

        data_b64 = base64.b64encode(raw).decode("ascii")
        size = len(raw)

        attachment_out: Dict[str, Any] = {
            "format": fmt,
            "data": data_b64,
        }
        # 필요하다면 사이즈도 추가로 전달
        attachment_out["size"] = size
        return attachment_out

    @staticmethod
    def _process_attachment_saved(saved: Optional[SavedFileInfo],
                                  att_src) -> Tuple[Optional[Path], Dict[str, Any] | None]:
        """
        첨부파일에 대해 확장자별로 redaction/detection 수행 후,
        에이전트로 돌려보낼 attachment JSON을 생성한다.

        return:
          (processed_path, response_attachment_dict)
        """
        if not saved:
            return None, None

        ext = (saved.ext or "").lower()
        processed_path: Optional[Path] = None

        try:
            # 1) 텍스트 기반 문서(DOCX/PPTX/XLSX/TXT/CSV) → detection 파일 생성
            #    (항상 *.detection.ext 로 저장)
            if ext in DOC_EXTS and ext != "pdf":
                process_saved_file(saved)  # 내부에서 detection 파일 생성
                processed_path = saved.path.with_name(
                    f"{saved.path.stem}.detection{saved.path.suffix}"
                )
            else:
                # 2) 이미지/스캔/PDF 등 → redaction 파이프라인
                red = redact_saved_file(saved)
                # red.redacted_path 가 없으면 original_path 사용
                processed_path = red.redacted_path or red.original_path
        except Exception:
            processed_path = None

        resp_attachment = DbLoggingService._build_response_attachment(att_src, processed_path)
        return processed_path, resp_attachment

    @staticmethod
    def handle(db: Session, item: InItem) -> ServerOut:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())

        # 1) 첨부 저장 (SavedFileInfo | None)
        saved_info: Optional[SavedFileInfo] = save_attachment_file(item)

        # 1-1) 첨부 파일 redaction/detection 수행 + 에이전트로 돌려보낼 attachment 준비
        processed_path: Optional[Path]
        response_attachment: Dict[str, Any] | None
        processed_path, response_attachment = DbLoggingService._process_attachment_saved(
            saved_info, item.attachment
        )

        # similarity 체크용 path/mime 분리
        saved_path: Optional[Path] = saved_info.path if saved_info else None
        saved_mime: Optional[str] = saved_info.mime if saved_info else None

        # 2) OCR (이미지 유사도 차단 등에서 사용)
        #    내부 구현에서 saved_path 를 다시 활용할 수 있음 (기존 OcrService 유지)
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
            [Entity(**e) for e in regex_ents_prompt if set(e).issuperset({"label", "value", "begin", "end"})]
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
            [Entity(**e) for e in prompt_entities if set(e).issuperset({"label", "value", "begin", "end"})]
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

        # 10) DB 저장 (프롬프트 엔티티만 저장, 첨부는 원본 그대로 직렬화)
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

        # 11) 응답 (에이전트로 '근거' + 처리된 첨부파일 전달)
        return ServerOut(
            request_id      = request_id,
            host            = rec.host,
            modified_prompt = rec.modified_prompt,
            has_sensitive   = rec.has_sensitive,
            entities        = [
                Entity(**e) for e in rec.entities
                if isinstance(e, dict) and set(e).issuperset({"value", "begin", "end", "label"})
            ],
            processing_ms   = rec.processing_ms,
            file_blocked    = rec.file_blocked,
            allow           = rec.allow,
            action          = rec.action,
            alert           = alert_text,
            attachment      = response_attachment,  # ✅ redaction/detection 적용된 파일
        )
