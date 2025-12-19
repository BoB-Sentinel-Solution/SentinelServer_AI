# services/db_logging.py
from __future__ import annotations

import uuid, time, os, base64
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging

from sqlalchemy.orm import Session

from schemas import InItem, ServerOut, Entity
from models import LogRecord, SettingsRecord  # ✅ SettingsRecord 추가
from services.ocr import OcrService
from services.masking import mask_by_entities, mask_with_parens_by_entities
from services.attachment import save_attachment_file, SavedFileInfo
from services.similarity import best_similarity_against_folder
from repositories.log_repo import LogRepository

from services.normalize_numbers import normalize_obfuscated_numbers

# 1) 정규식 1차 감지기
from services.regex_detector import detect_entities as regex_detect
# 2) 외부 판별기 러너(offline_sensitive_detector_min.py 호출)
from services.ai_external import OfflineDetectorRunner

# 3) 파일 처리(문서 detection / 이미지·PDF redaction)
from services.files import process_saved_file, redact_saved_file, DOC_EXTS

logger = logging.getLogger(__name__)

ADMIN_IMAGE_DIR = Path("./SentinelServer_AI/adminset/image")
SIMILARITY_THRESHOLD = 0.4  # 이미지 유사도 차단 임계

# 러너 싱글턴 (MODEL_DIR, MAX_NEW_TOKENS는 .env에서 읽힘)
_DETECTOR = OfflineDetectorRunner(
    model_dir=os.environ.get("MODEL_DIR", "").strip() or None,
    timeout_sec=20.0,
)

# =========================
# Settings 기반 서비스 필터
# =========================

LLM_HOST_MAP = {
    "gpt": "chatgpt",
    "gemini": "gemini",
    "claude": "claude",
    "deepseek": "deepseek",
    "groq": "groq",

    # 추가 LLM
    "grok": "grok.com",
    "perplexity": "perplexity.ai",
    "poe": "poe.com",
    "mistral": "mistral.ai",
    "cohere": "cohere.com",
    "huggingface": "huggingface.co",
    "you": "you.com",
    "openrouter": "openrouter.ai",
}


MCP_HOST_MAP = {
    "gpt_desktop": "chatgpt",
    "claude_desktop": "claude",
    "vscode_copilot": "copilot",
}


def _load_settings_config(db: Session) -> Dict[str, Any]:
    """
    settings(id=1)에서 config_json(dict)을 읽어옴.
    - 테이블/레코드 없거나 예외면 {} 반환
    """
    try:
        rec = db.get(SettingsRecord, 1)
        if not rec:
            return {}
        cfg = rec.config_json
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _is_monitored_by_settings(cfg: Dict[str, Any], interface: str, host: str) -> bool:
    itf = (interface or "llm").strip().lower()
    h = (host or "").strip().lower()

    # ✅ 세팅 미적용(기본): 전부 ON
    sf = cfg.get("service_filters") if isinstance(cfg, dict) else None
    if not isinstance(sf, dict):
        return True

    enabled = sf.get(itf)
    if not isinstance(enabled, dict):
        # ✅ interface 설정이 없으면 기본 ON (denylist 정책)
        return True

    # ✅ 전부 체크 해제면 “전부 모니터링 OFF”
    if not any(bool(v) for v in enabled.values()):
        return False

    mapping = LLM_HOST_MAP if itf == "llm" else (MCP_HOST_MAP if itf == "mcp" else None)
    if mapping is None:
        return True  # 모르는 interface는 기존처럼 ON (원하면 False로 바꿔도 됨)

    # ✅ host가 매핑되면: 체크 상태 그대로 반영(체크 해제 시 OFF)
    for key, substr in mapping.items():
        if substr in h:
            return bool(enabled.get(key, True))

    # ✅ 매핑에 없는 host는 기본 ON
    return True

# =========================
# 기존 유틸
# =========================

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

def _merge_raw_and_norm_drop_overlap(
    raw: List[Dict[str, Any]],
    norm: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    raw 우선 병합.
    norm 엔티티는 raw의 어떤 엔티티와도 스팬이 '조금이라도' 겹치면 버린다(라벨 무관).
    겹치지 않는 norm만 raw 뒤에 붙인다.
    """
    out = list(raw)

    for e in norm:
        eb, ee = int(e.get("begin", -1)), int(e.get("end", -1))
        if eb < 0 or ee < 0 or ee <= eb:
            continue

        overlapped = False
        for x in raw:
            xb, xe = int(x.get("begin", -1)), int(x.get("end", -1))
            if xb < 0 or xe < 0 or xe <= xb:
                continue
            # ✅ 조금이라도 겹치면 overlap
            if not (ee <= xb or xe <= eb):
                overlapped = True
                break

        if overlapped:
            continue

        out.append(e)

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


def _build_alert_from_merged(
    merged_ents: List[Dict[str, Any]],
    regex_src: List[Dict[str, Any]],
    ai_src: List[Dict[str, Any]]
) -> str:
    """
    최종 병합된 엔티티(= 실제 마스킹/저장에 쓰이는 것) 기준으로,
    각 엔티티의 '출처'를 정규식/AI로 태깅하여 라벨을 소스별로 집계.
    """
    regex_keys = {_ent_key(e) for e in regex_src}
    ai_keys = {_ent_key(e) for e in ai_src}

    labels_regex: List[str] = []
    labels_ai: List[str] = []

    for e in merged_ents:
        k = _ent_key(e)
        lab = str(e.get("label", "")).upper()
        if k in regex_keys and k in ai_keys:
            labels_regex.append(lab)
        elif k in regex_keys:
            labels_regex.append(lab)
        elif k in ai_keys:
            labels_ai.append(lab)

    only_regex = sorted(set(labels_regex))
    only_ai = sorted(set(labels_ai))

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
        if isinstance(att, dict):
            return dict(att)
        return None

    @staticmethod
    def _get_attachment_format(att) -> Optional[str]:
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
    def _build_response_attachment(att_src, processed_path: Optional[Path], file_changed: bool = False) -> Dict[str, Any] | None:
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
            "size": size,
            "file_change": bool(file_changed),
        }
        return attachment_out

    @staticmethod
    def _process_attachment_saved(
        saved: Optional[SavedFileInfo],
        att_src,
        monitored: bool,
    ) -> Tuple[Optional[Path], Dict[str, Any] | None]:
        if not saved:
            return None, None

        # ✅ 서비스 미선택이면 첨부는 “원본 그대로” 반환(레댁션/디텍션 스킵)
        if not monitored:
            processed_path = saved.path
            resp_attachment = DbLoggingService._build_response_attachment(
                att_src, processed_path, file_changed=False
            )
            return processed_path, resp_attachment

        ext = (saved.ext or "").lower()
        processed_path: Optional[Path] = None
        file_changed: bool = False

        try:
            # 1) 텍스트 기반 문서(DOCX/PPTX/XLSX/TXT/CSV) → 민감정보 있을 때만 detection 파일 생성
            if ext in DOC_EXTS and ext != "pdf":
                logger.info(f"[ATTACH] process_saved_file: {saved.path} (ext={ext})")
                process_saved_file(saved)

                detection_path = saved.path.with_name(
                    f"{saved.path.stem}.detection{saved.path.suffix}"
                )

                if detection_path.exists():
                    processed_path = detection_path
                    file_changed = True
                else:
                    processed_path = saved.path
                    file_changed = False

            # 2) 이미지/스캔/PDF 등 → redaction 파이프라인
            else:
                logger.info(f"[ATTACH] redact_saved_file: {saved.path} (ext={ext})")
                red = redact_saved_file(saved)
                logger.info(
                    f"[ATTACH] redacted result: original={red.original_path}, "
                    f"redacted={red.redacted_path}, performed={red.redaction_performed}, "
                    f"error={red.redaction_error}"
                )
                processed_path = red.redacted_path or red.original_path

                if red.redaction_performed and red.redacted_path and red.redacted_path != red.original_path:
                    file_changed = True

        except Exception as e:
            logger.exception(f"[ATTACH] _process_attachment_saved error: {e}")
            processed_path = None
            file_changed = False

        resp_attachment = DbLoggingService._build_response_attachment(
            att_src,
            processed_path,
            file_changed=file_changed,
        )
        return processed_path, resp_attachment

    @staticmethod
    def handle(db: Session, item: InItem) -> ServerOut:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())

        # ✅ Settings 로드 + 서비스 모니터링 여부 결정
        cfg = _load_settings_config(db)
        interface = item.interface or "llm"
        host = item.host or ""
        monitored = _is_monitored_by_settings(cfg, interface, host)

        # 1) 첨부 저장 (SavedFileInfo | None) => 원본 파일은 항상 저장
        saved_info: Optional[SavedFileInfo] = save_attachment_file(item)

        # 1-1) 첨부 파일 처리 + 응답 attachment 준비 (모니터링 OFF면 원본 그대로)
        processed_path: Optional[Path]
        response_attachment: Dict[str, Any] | None
        processed_path, response_attachment = DbLoggingService._process_attachment_saved(
            saved_info, item.attachment, monitored=monitored
        )

        saved_path: Optional[Path] = saved_info.path if saved_info else None
        saved_mime: Optional[str] = saved_info.mime if saved_info else None

        # 2) OCR (모니터링 OFF면 스킵)
        if monitored:
            ocr_text, ocr_used, _ = OcrService.run_ocr(item)
        else:
            ocr_text, ocr_used = "", False

        # (강화) OCR 텍스트에도 정규식 적용 (모니터링 ON일 때만)
        if monitored and ocr_used and ocr_text:
            try:
                regex_ents_ocr_raw = regex_detect(ocr_text)
            except Exception:
                regex_ents_ocr_raw = []

            ocr_norm = normalize_obfuscated_numbers(ocr_text)
            try:
                regex_ents_ocr_norm = regex_detect(ocr_norm)
            except Exception:
                regex_ents_ocr_norm = []

            for e in regex_ents_ocr_norm:
                b, en = int(e.get("begin", -1)), int(e.get("end", -1))
                if 0 <= b < en <= len(ocr_text):
                    e["value"] = ocr_text[b:en]

            regex_ents_ocr = _merge_raw_and_norm_drop_overlap(
                regex_ents_ocr_raw,
                regex_ents_ocr_norm,
            )

        else:
            regex_ents_ocr = []

        file_has_sensitive = bool(regex_ents_ocr)

        # 3) 프롬프트
        prompt_text = item.prompt or ""

        # ✅ 모니터링 OFF면 프롬프트 탐지/AI/마스킹 스킵
        if not monitored:
            regex_ents_prompt: List[Dict[str, Any]] = []
            ai_ents_rebased: List[Dict[str, Any]] = []
            prompt_entities: List[Dict[str, Any]] = []

            det_ai = {"has_sensitive": False, "entities": [], "processing_ms": 0}
            ai_ms = 0

            has_sensitive = False
            file_has_sensitive = False  # 첨부도 스킵했으니 민감도 반영 안 함
            file_blocked = False
            allow = True
            action = "allow_unmonitored"

            final_modified_prompt = prompt_text
            alert_text = ""

        else:
            # 3-1) 원문 기반 탐지
            try:
                regex_ents_prompt_raw: List[Dict[str, Any]] = regex_detect(prompt_text)
            except Exception:
                regex_ents_prompt_raw = []

            # 3-2) 수사 치환본 기반 탐지
            prompt_norm = normalize_obfuscated_numbers(prompt_text)
            try:
                regex_ents_prompt_norm: List[Dict[str, Any]] = regex_detect(prompt_norm)
            except Exception:
                regex_ents_prompt_norm = []

            # 3-3) norm 탐지 결과 value 복구
            for e in regex_ents_prompt_norm:
                b, en = int(e.get("begin", -1)), int(e.get("end", -1))
                if 0 <= b < en <= len(prompt_text):
                    e["value"] = prompt_text[b:en]

            # 3-4) 병합
            regex_ents_prompt = _merge_raw_and_norm_drop_overlap(
                regex_ents_prompt_raw,
                regex_ents_prompt_norm,
            )

            # 4) AI 입력용 마스킹(정규식 결과만, 괄호 포함)
            masked_for_ai = mask_with_parens_by_entities(
                prompt_text,
                [Entity(**e) for e in regex_ents_prompt if set(e).issuperset({"label", "value", "begin", "end"})]
            )

            # 5) AI 보완 탐지
            try:
                det_ai = _DETECTOR.analyze_text(masked_for_ai, return_spans=False)
            except Exception:
                det_ai = {"has_sensitive": False, "entities": [], "processing_ms": 0}

            ai_raw_ents = det_ai.get("entities", []) or []
            ai_ms = int(det_ai.get("processing_ms", 0) or 0)

            # 6) AI 결과를 원문 기준 스팬으로 재계산 → 정규식 결과와 병합
            ai_ents_rebased = _rebase_ai_entities_on_original(prompt_text, ai_raw_ents)
            prompt_entities = _dedup_spans(regex_ents_prompt, ai_ents_rebased)

            has_sensitive = bool(
                prompt_entities
                or regex_ents_ocr
                or bool(det_ai.get("has_sensitive"))
            )

            # 7) 정책결정
            # - settings.config_json 의 response_method 를 실제 allow/action에 반영
            #   * mask  : 민감 시 마스킹 후 허용
            #   * allow : 민감 시 원문 그대로 허용
            #   * block : 민감 시 차단(allow=False)
            response_method = (cfg.get("response_method") or "mask").strip().lower()

            # 파일 민감 탐지는 "민감 여부"로만 두고,
            # 실제 차단 여부(file_blocked)는 action/allow와 일치하게 운용한다.
            file_sensitive = bool(file_has_sensitive)
            file_blocked = False
            allow = True

            # 민감 여부(프롬프트/파일/OCR/AI 플래그 포함)
            sensitive_any = bool(
                prompt_entities
                or regex_ents_ocr
                or bool(det_ai.get("has_sensitive"))
            )

            # 기본값
            action = "allow"

            if sensitive_any:
                if response_method == "block":
                    allow = False
                    action = "block_sensitive"
                    # block 모드에서도 응답에 원문을 그대로 주면 위험하니 마스킹된 프롬프트를 내려주는 편이 안전
                    final_modified_prompt = mask_by_entities(
                        prompt_text,
                        [Entity(**e) for e in prompt_entities if set(e).issuperset({"label", "value", "begin", "end"})]
                    )
                    # 파일에서 민감이 탐지된 경우 "파일 차단"으로도 표시
                    if file_sensitive:
                        file_blocked = True
                        action = "block_file_sensitive"

                elif response_method == "allow":
                    allow = True
                    action = "allow_sensitive"
                    # allow 모드에서는 원문 그대로
                    final_modified_prompt = prompt_text

                else:
                    # 기본: mask
                    allow = True
                    action = "mask_and_allow"
                    final_modified_prompt = mask_by_entities(
                        prompt_text,
                        [Entity(**e) for e in prompt_entities if set(e).issuperset({"label", "value", "begin", "end"})]
                    )
            else:
                # 민감 없음
                allow = True
                action = "allow"
                final_modified_prompt = prompt_text

            # 이미지 유사도 차단(기존 로직 유지) — response_method보다 우선 차단됨
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

            # 8) 최종 마스킹(정규식 + AI 보완 엔티티, 괄호 없음)
            # - 위 정책결정에서 final_modified_prompt를 이미 결정했으므로 여기서는 재마스킹하지 않음
            #   (중복 마스킹/불필요 계산 방지)
            # final_modified_prompt = mask_by_entities(
            #     prompt_text,
            #     [Entity(**e) for e in prompt_entities if set(e).issuperset({"label", "value", "begin", "end"})]
            # )

            # 9) alert 생성
            alert_text = _build_alert_from_merged(
                merged_ents=prompt_entities,
                regex_src=regex_ents_prompt,
                ai_src=ai_ents_rebased,
            )
            if not alert_text and prompt_entities:
                labels = sorted({e["label"] for e in prompt_entities})
                if labels:
                    alert_text = f"Detected: {', '.join(labels)}"

        # 처리시간
        processing_ms = max(int((time.perf_counter() - t0) * 1000), int(ai_ms or 0))

        host_name = item.hostname or item.pc_name

        # 10) DB 저장
        rec = LogRecord(
            request_id=request_id,
            time=item.time,
            public_ip=item.public_ip,
            private_ip=item.private_ip,
            host=item.host or "unknown",
            hostname=host_name,
            prompt=prompt_text,
            attachment=DbLoggingService._serialize_attachment(item.attachment),
            interface=item.interface or "llm",

            modified_prompt=final_modified_prompt,
            has_sensitive=bool(has_sensitive),
            entities=[dict(e) for e in (prompt_entities or [])],
            processing_ms=processing_ms,

            file_blocked=bool(file_blocked),
            allow=bool(allow),
            action=str(action),
        )
        LogRepository.create(db, rec)

        # 11) 응답
        return ServerOut(
            request_id=rec.request_id,
            host=rec.host,
            modified_prompt=rec.modified_prompt,
            has_sensitive=rec.has_sensitive,
            entities=[
                Entity(**e) for e in (rec.entities or [])
                if isinstance(e, dict) and set(e).issuperset({"value", "begin", "end", "label"})
            ],
            processing_ms=rec.processing_ms,
            file_blocked=rec.file_blocked,
            allow=rec.allow,
            action=rec.action,
            alert=alert_text if monitored else "",
            attachment=response_attachment,
        )
