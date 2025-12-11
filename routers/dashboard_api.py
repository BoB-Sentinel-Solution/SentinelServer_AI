# routers/dashboard_api.py
from __future__ import annotations

import json
import re
import ipaddress
from typing import Dict, List, Any
from collections import defaultdict, Counter
from datetime import datetime, date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import cast, Text, func  # JSON 검색 + interface 필터용

from db import SessionLocal, Base, engine
from models import LogRecord, McpConfigEntry
from config import settings
from services.reason_llm import infer_intent_with_llm
  
# 접두는 app.py에서 prefix="/api"로 부여
router = APIRouter()

# https://123.45.67.89/ 이런 형태의 URL 탐지용 정규표현식
IP_URL_RE = re.compile(
    r"^https?://(?:(?:\d{1,3}\.){3}\d{1,3})(?::\d+)?(?:/|$)",
    re.IGNORECASE,
)

# 운영에서는 Alembic 권장. 개발 편의를 위해 안전 생성.
Base.metadata.create_all(bind=engine)

def _parse_attachment(att) -> dict:
    """
    log_records.attachment 컬럼을 Python dict로 통일해서 리턴.
    - DB에는 TEXT(JSON 문자열)로 들어가 있을 수도 있고
    - SQLAlchemy에서 이미 dict로 올라올 수도 있으니 둘 다 처리.
    """
    if not att:
        return {}

    # 이미 dict인 경우 (SQLAlchemy JSON 타입 등)
    if isinstance(att, dict):
        return att or {}

    # 문자열인 경우: JSON 디코드 후 dict일 때만 사용
    if isinstance(att, str):
        try:
            obj = json.loads(att)
            if isinstance(obj, dict):
                return obj
            else:
                return {}
        except Exception:
            return {}

    # 그 외 타입은 전부 무시
    return {}

# --- DB 세션 DI ---
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- 선택적 API 키 인증 ---
def require_admin(x_admin_key: str | None = Header(default=None)):
    """
    - .env 의 DASHBOARD_API_KEY 가 설정되어 있다면 X-Admin-Key 헤더로 검증
    - 없으면 무인증 허용
    """
    if settings.DASHBOARD_API_KEY:
        if x_admin_key != settings.DASHBOARD_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

# ---------------------------
# Reason / Risk 패턴 정의
# ---------------------------

_RISK_PATTERNS = [
    # 1. 신원 정보 유출
    {
        "category": "신원 정보 유출",
        "labels": {"NAME", "PHONE", "ADDRESS"},
        "pattern": "NAME + PHONE + ADDRESS",
        "description": "개인을 특정하고 직접 연락 및 방문하여 피싱 가능",
    },
    {
        "category": "신원 정보 유출",
        "labels": {"NAME", "EMAIL", "ADDRESS", "POSTAL_CODE"},
        "pattern": "NAME + EMAIL + ADDRESS + POSTAL_CODE",
        "description": "온라인·오프라인 모두에서 특정인을 정밀하게 타겟팅 가능",
    },

    # 2. 신원 도용 · 본인인증 우회 계열
    {
        "category": "신원 도용 · 본인인증 우회 계열",
        "labels": {"PASSPORT", "NAME", "ADDRESS"},
        "pattern": "PASSPORT + NAME + ADDRESS",
        "description": "여권 정보와 거주지가 결합되어 해외 출입·신분 사칭에 악용 가능",
    },
    {
        "category": "신원 도용 · 본인인증 우회 계열",
        "labels": {"DRIVER_LICENSE", "NAME", "PHONE"},
        "pattern": "DRIVER_LICENSE + NAME + PHONE",
        "description": "실명·연락처·공적 신분증 번호가 묶여 각종 본인인증 우회에 사용될 수 있음",
    },
    {
        "category": "신원 도용 · 본인인증 우회 계열",
        "labels": {"BUSINESS_ID", "NAME", "PHONE"},
        "pattern": "BUSINESS_ID + NAME + PHONE",
        "description": "특정 사업자를 정확히 식별해 피싱·사기성 비즈니스 메일 타겟팅에 악용 가능",
    },
    {
        "category": "신원 도용 · 본인인증 우회 계열",
        "labels": {"RESIDENT_ID", "NAME", "PHONE"},
        "pattern": "RESIDENT_ID + NAME + PHONE",
        "description": "실명 확인 체계와 직접적인 연관성이 있어 각종 본인인증 우회·금융사기 가능",
    },

    # 3. 금융 · 결제 탈취 계열
    {
        "category": "금융 · 결제 탈취 계열",
        "labels": {"CARD_NUMBER", "CARD_EXPIRY", "CARD_CVV"},
        "pattern": "CARD_NUMBER + CARD_EXPIRY + CARD_CVV",
        "description": "온라인 결제에 필요한 카드번호·유효기간·CVV가 모두 포함되어 카드 실물 없이 결제가 가능",
    },
    {
        "category": "금융 · 결제 탈취 계열",
        "labels": {"CARD_NUMBER", "CARD_CVV", "PAYMENT_PIN"},
        "pattern": "CARD_NUMBER + CARD_CVV + PAYMENT_PIN",
        "description": "카드 정보와 인증 수단이 동시에 노출되어 고액 결제·인출에 직접 사용 가능",
    },
    {
        "category": "금융 · 결제 탈취 계열",
        "labels": {"MNEMONIC", "PAYMENT_URI_QR"},
        "pattern": "MNEMONIC + PAYMENT_URI_QR",
        "description": "지갑 복구용 시드와 송금 대상 정보가 함께 노출되어 가상자산 전체 탈취 가능",
    },
    {
        "category": "금융 · 결제 탈취 계열",
        "labels": {"CRYPTO_PRIVATE_KEY", "PAYMENT_URI_QR"},
        "pattern": "CRYPTO_PRIVATE_KEY + PAYMENT_URI_QR",
        "description": "특정 지갑 주소와 대응하는 프라이빗키가 함께 노출되어 잔액을 즉시 이체할 수 있음",
    },
    {
        "category": "금융 · 결제 탈취 계열",
        "labels": {"HD_WALLET", "MNEMONIC"},
        "pattern": "HD_WALLET + MNEMONIC",
        "description": "다수 지갑을 생성하는 상위 키와 시드가 동시에 유출되어 여러 주소를 장악 가능",
    },

    # 4. 위치·접근 위협 계열
    {
        "category": "위치·접근 위협 계열",
        "labels": {"NAME", "ADDRESS", "POSTAL_CODE"},
        "pattern": "NAME + ADDRESS + POSTAL_CODE",
        "description": "특정 개인의 실제 거주 위치를 매우 정밀하게 식별 가능",
    },
    {
        "category": "위치·접근 위협 계열",
        "labels": {"PHONE", "ADDRESS", "POSTAL_CODE"},
        "pattern": "PHONE + ADDRESS + POSTAL_CODE",
        "description": "이름이 없어도 실제 거주지 기반 스토킹·피싱·방문 위협이 가능",
    },
]

# ---------- 위험 라벨 조합 (캐러셀용) ----------

DANGEROUS_LABEL_COMBOS: List[List[str]] = [
    # 1. 신원 정보 유출
    ["NAME", "PHONE", "ADDRESS"],
    ["NAME", "EMAIL", "ADDRESS", "POSTAL_CODE"],
    # 2. 신원 도용 · 본인인증 우회 계열
    ["PASSPORT", "NAME", "ADDRESS"],
    ["DRIVER_LICENSE", "NAME", "PHONE"],
    ["BUSINESS_ID", "NAME", "PHONE"],
    ["RESIDENT_ID", "NAME", "PHONE"],
    # 3. 금융 · 결제 탈취 계열
    ["CARD_NUMBER", "CARD_EXPIRY", "CARD_CVV"],
    ["CARD_NUMBER", "CARD_CVV", "PAYMENT_PIN"],
    ["MNEMONIC", "PAYMENT_URI_QR"],
    ["CRYPTO_PRIVATE_KEY", "PAYMENT_URI_QR"],
    ["HD_WALLET", "MNEMONIC"],
    # 4. 위치·접근 위협 계열
    ["NAME", "ADDRESS", "POSTAL_CODE"],
    ["PHONE", "ADDRESS", "POSTAL_CODE"],
]


def _extract_label_set(entities: List[Dict[str, Any]]) -> set[str]:
  """엔티티 배열에서 라벨만 모아 대문자 set으로 반환."""
  labels: set[str] = set()
  for e in entities or []:
      lab = (e.get("label") or e.get("LABEL") or "").upper()
      if lab:
          labels.add(lab)
  return labels


def detect_combo_labels(entities: List[Dict[str, Any]]) -> List[str]:
  """
  사전에 정의한 라벨 조합이 있는지 확인해서,
  발견되면 그 콤보 라벨 리스트를 그대로 반환.
  없으면, 중요정보가 5개 이상이면 그 라벨 집합을 반환(복합 위협),
  그 외엔 빈 리스트.
  """
  label_set = _extract_label_set(entities)
  if not label_set:
      return []

  # 3~4개짜리 사전 정의 조합 먼저 탐지
  for combo in DANGEROUS_LABEL_COMBOS:
      s = set(combo)
      if s.issubset(label_set):
          # 프론트에서 rule.labels와 정확히 비교하므로
          # 콤보에 들어있는 라벨만 그대로 넘겨준다.
          return combo

  # 복합 정보 결합 위협: 중요정보 5개 이상
  if len(label_set) >= 5:
      return sorted(label_set)

  return []


def classify_risk_from_entities(entities: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    엔티티 라벨 조합으로 위험 카테고리/패턴/설명을 판별.
    매칭이 없으면 '기타' 또는 '복합 정보 결합 위협'으로 분류.
    """
    labels = {
        (e.get("label") or "").upper()
        for e in (entities or [])
        if e.get("label")
    }
    labels = {lab for lab in labels if lab}

    # 정의된 패턴 우선 체크
    for pat in _RISK_PATTERNS:
        if pat["labels"].issubset(labels):
            return {
                "category": pat["category"],
                "pattern": pat["pattern"],
                "description": pat["description"],
            }

    # 중요 정보 5개 이상 동시 탐지 → 복합 정보 결합 위협
    if len(labels) >= 5:
        return {
            "category": "복합 정보 결합 위협",
            "pattern": "중요정보 5개 이상 동시 탐지",
            "description": "중요정보 5개 이상이 동시에 포함되어 복합적인 공격 가능성이 높음",
        }

    # 그 외는 기타
    return {
        "category": "기타",
        "pattern": " / ".join(sorted(labels)) if labels else "",
        "description": "사전 정의되지 않은 조합의 중요정보가 탐지되었습니다.",
    }


_HIGH_INTENT_LABELS = {
    "CARD_NUMBER",
    "CARD_CVV",
    "CARD_EXPIRY",
    "MNEMONIC",
    "CRYPTO_PRIVATE_KEY",
    "HD_WALLET",
    "PAYMENT_PIN",
    "MOBILE_PAYMENT_PIN",
    "RESIDENT_ID",
    "PASSPORT",
    "DRIVER_LICENSE",
}


def infer_intent_and_reason_from_context(
    context_logs: List[LogRecord],
    risk_info: Dict[str, str],
) -> tuple[str, str]:
    """
    [임시 휴리스틱 버전]
    - 여기 부분을 나중에 로컬 LLM 호출로 교체하면 됨.
    - 현재는 고위험 금융/신분 계열 라벨 유무 + 반복 여부를 보고 의도/부주의를 나눔.
    """
    if not context_logs:
        return "unknown", "맥락 로그가 부족하여 의도성을 판단하기 어렵습니다."

    target = context_logs[-1]
    labels = {
        (e.get("label") or "").upper()
        for e in (target.entities or [])
        if e.get("label")
    }

    # 단순 휴리스틱: 고위험 라벨이 포함되어 있으면 'intentional'
    if labels & _HIGH_INTENT_LABELS:
        intent = "intentional"
    else:
        intent = "negligent"

    prev_cnt = len(context_logs) - 1
    pattern = risk_info.get("pattern") or "중요정보 조합"

    if intent == "intentional":
        if prev_cnt >= 2:
            reason = (
                f"동일 PC에서 최근 {prev_cnt + 1}회 연속으로 고위험 조합({pattern})이 "
                "포함된 요청이 발생해 의도적인 유출 가능성이 높다고 판단됩니다."
            )
        else:
            reason = (
                f"고위험 조합({pattern})이 한 번에 포함되어 단순 실수보다는 "
                "의도적인 정보 제공 가능성이 더 큽니다."
            )
    else:
        reason = (
            f"프롬프트 내에 {pattern}이 포함되었으나 반복성이 낮고 업무성 문맥으로 보여 "
            "사용자 부주의 가능성이 더 높은 것으로 판단됩니다."
        )

    return intent, reason

# ---------- 요약 API ----------
@router.get("/summary", dependencies=[Depends(require_admin)])
def dashboard_summary(
    interface: str | None = None,  # ?interface=LLM / MCP 등 필터
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    대시보드 요약 데이터:
    - total_sensitive: has_sensitive=True 총 건수
    - total_blocked: 차단된 요청 수 (allow=False 또는 action startswith("block"))
    - type_ratio: 라벨 비율(엔티티 라벨 카운트, 전체 기간)
    - type_detected: 유형별 탐지 횟수(전체 기간)
    - type_blocked: 유형별 차단 횟수(파일 유사 차단은 FILE_SIMILAR)
    - hourly_attempts: 0~23시 카운트(모든 요청, 전체 기간)
    - hourly_type: 시간대별(0~23) · 라벨별 탐지 건수 (has_sensitive=True)
    - recent_logs: 최근 20건 (민감값 미노출)
    - ip_band_detected / ip_band_blocked: 공인IP /16 대역별 탐지/차단 건수

    - today_sensitive / today_blocked: 오늘 탐지·차단 건수
    - today_hourly: 오늘 시간대별 탐지 건수 [0..23]
    - today_type_ratio: 오늘 탐지된 라벨 비율

    서비스 기반 리포트용:
    - service_usage_by_host: 호스트별 전체 호출 수
    - service_sensitive_by_host: 호스트별 민감정보 탐지 수
    - service_blocked_by_host: 호스트별 차단 수

    파일 기반 리포트용:
    - file_detect_by_ext: 확장자별(attachment.format) 민감정보 탐지 건수
    - file_label_by_ext: 확장자+라벨별 탐지 건수
    - recent_file_logs: 최근 파일 첨부 요청(최대 20건)

    interface 파라미터가 주어지면 해당 interface 로그만 집계 (예: LLM, MCP)
    """

    # --- 쿼리 구성: interface 있으면 필터 ---
    query = db.query(LogRecord)
    if interface:
        q_interface = interface.strip().lower()
        query = query.filter(func.lower(LogRecord.interface) == q_interface)

    rows: List[LogRecord] = query.order_by(LogRecord.created_at.desc()).all()

    # 오늘 날짜 (created_at 이 timezone-aware 라면 적절히 맞춰야 함)
    today: date = datetime.utcnow().date()

    total_sensitive = 0
    total_blocked = 0

    type_ratio: Dict[str, int] = defaultdict(int)
    type_detected: Dict[str, int] = defaultdict(int)

    # 새로 추가된 "탐지" 집계
    ip_band_detected: Dict[str, int] = defaultdict(int)

    # 기존 "차단" 집계(호환 유지)
    type_blocked: Dict[str, int] = defaultdict(int)
    ip_band_blocked: Dict[str, int] = defaultdict(int)

    # 서비스(호스트)별 집계
    service_usage_by_host: Dict[str, int] = defaultdict(int)
    service_sensitive_by_host: Dict[str, int] = defaultdict(int)
    service_blocked_by_host: Dict[str, int] = defaultdict(int)

    # 파일 기반 집계
    file_detect_by_ext: Dict[str, int] = defaultdict(int)
    file_label_by_ext: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    recent_file_logs: List[Dict[str, Any]] = []

    # 오늘 기준 통계
    today_sensitive = 0
    today_blocked = 0
    today_type_ratio: Dict[str, int] = defaultdict(int)

    # 시간대별 통계
    hourly_attempts = [0] * 24                 # 전체 요청 수
    today_hourly = [0] * 24                    # 오늘 탐지 건수
    hourly_type: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    recent_logs: List[Dict[str, Any]] = []

    for r in rows:
        created = r.created_at
        created_date: date | None = created.date() if created else None
        hour: int | None = created.hour if created else None

        # ---- 서비스(호스트)별 공통 집계 ----
        host_key = r.host or "unknown"
        service_usage_by_host[host_key] += 1

        # ---- 파일 관련 정보 파싱 (attachment.format) ----
        file_ext: str | None = None
        att = r.attachment
        if att:
            if isinstance(att, dict):
                file_ext = (att.get("format") or "").strip().lower() or None
            elif isinstance(att, str):
                try:
                    att_json = json.loads(att)
                    file_ext = (att_json.get("format") or "").strip().lower() or None
                except Exception:
                    file_ext = None

        # ---- 공통: 시간대별 "시도" 카운트 (모든 요청) ----
        if hour is not None and 0 <= hour < 24:
            try:
                hourly_attempts[hour] += 1
            except Exception:
                pass

        # ---- 차단 여부 미리 계산 ----
        action = (r.action or "")
        is_blocked = (r.allow is False) or action.startswith("block")

        # === 탐지 관련 집계 ===
        if r.has_sensitive:
            total_sensitive += 1
            service_sensitive_by_host[host_key] += 1

            # 유형 비율/탐지 횟수: 엔티티 라벨 기준
            for e in (r.entities or []):
                label = e.get("label", "OTHER")
                type_ratio[label] += 1
                type_detected[label] += 1

                # 시간대별 유형 카운트
                if hour is not None and 0 <= hour < 24:
                    hourly_type[hour][label] += 1

                # 오늘 기준 유형 비율
                if created_date == today:
                    today_type_ratio[label] += 1

                # 파일 기반: 확장자+라벨별 카운트
                if file_ext:
                    file_label_by_ext[file_ext][label] += 1

            # /16 대역 탐지 건수
            if r.public_ip and r.public_ip.count(".") == 3:
                a, b, *_ = r.public_ip.split(".")
                ip_band_detected[f"{a}.{b}.*"] += 1

            # 오늘 탐지 건수 / 시간대별
            if created_date == today and hour is not None and 0 <= hour < 24:
                today_sensitive += 1
                try:
                    today_hourly[hour] += 1
                except Exception:
                    pass

            # 파일 기반: 확장자별 탐지 건수
            if file_ext:
                file_detect_by_ext[file_ext] += 1

        # === 차단 관련 집계(기존 로직 유지) ===
        if is_blocked:
            total_blocked += 1
            service_blocked_by_host[host_key] += 1

            if created_date == today:
                today_blocked += 1

            if r.entities:
                for e in r.entities:
                    type_blocked[e.get("label", "OTHER")] += 1
            # 파일 유사 차단인데 엔티티가 없을 때는 FILE_SIMILAR로 표기
            if r.file_blocked and not r.entities:
                type_blocked["FILE_SIMILAR"] += 1

            if r.public_ip and r.public_ip.count(".") == 3:
                a, b, *_ = r.public_ip.split(".")
                ip_band_blocked[f"{a}.{b}.*"] += 1

        # === 최근 로그 20건 (민감값 미노출) ===
        if len(recent_logs) < 20:
            recent_logs.append({
                "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                "host": r.host,
                "hostname": r.hostname,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "internal_ip": r.private_ip,  # 대시보드 테이블에서 쓰는 필드
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "entities": [{"label": (e.get("label") or "")} for e in (r.entities or [])],
                "prompt": (r.prompt[:120] + "…") if r.prompt and len(r.prompt) > 120 else (r.prompt or ""),
            })

        # === 최근 파일 로그 20건 (첨부 있는 경우만) ===
        if file_ext and len(recent_file_logs) < 20:
            recent_file_logs.append({
                "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                "host": r.host,
                "hostname": r.hostname,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "internal_ip": r.private_ip,  # 대시보드 테이블에서 쓰는 필드
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "blocked": is_blocked,
                "file_ext": file_ext,
            })

    # hourly_type 은 {시간(int): {라벨:카운트}} → JSON 직렬화 위해 키를 문자열로
    hourly_type_serialized: Dict[str, Dict[str, int]] = {
        str(h): dict(type_counts) for h, type_counts in hourly_type.items()
    }

    # file_label_by_ext 도 dict 로 변환
    file_label_by_ext_serialized: Dict[str, Dict[str, int]] = {
        ext: dict(label_counts) for ext, label_counts in file_label_by_ext.items()
    }

    return {
        # 전체 기간 통계
        "total_sensitive": total_sensitive,
        "total_blocked": total_blocked,
        "type_ratio": dict(type_ratio),
        "type_detected": dict(type_detected),
        "type_blocked": dict(type_blocked),
        "hourly_attempts": hourly_attempts,
        "hourly_type": hourly_type_serialized,
        "recent_logs": recent_logs,
        "ip_band_detected": dict(ip_band_detected),
        "ip_band_blocked": dict(ip_band_blocked),

        # 서비스(호스트)별 통계
        "service_usage_by_host": dict(service_usage_by_host),
        "service_sensitive_by_host": dict(service_sensitive_by_host),
        "service_blocked_by_host": dict(service_blocked_by_host),

        # 파일 기반 통계
        "file_detect_by_ext": dict(file_detect_by_ext),
        "file_label_by_ext": file_label_by_ext_serialized,
        "recent_file_logs": recent_file_logs,

        # 오늘 기준 통계
        "today_sensitive": today_sensitive,
        "today_blocked": today_blocked,
        "today_hourly": today_hourly,
        "today_type_ratio": dict(today_type_ratio),
    }


# ---------- 전체 로그 조회 API (Logs 페이지용) ----------
@router.get("/logs", dependencies=[Depends(require_admin)])
def list_logs(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Logs 페이지용 전체 로그 조회 API

    쿼리 파라미터:
    - page: 페이지 번호(1부터)
    - page_size: 페이지 크기 (최대 500)
    - q: 검색 키워드
    - category: 검색 대상 컬럼
      - prompt | host | pc_name | public_ip | private_ip | entity
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 500:
        page_size = 500

    query = db.query(LogRecord)

    # 검색 필터
    if q:
        like = f"%{q}%"
        cat = (category or "").lower()

        if cat == "prompt":
            query = query.filter(LogRecord.prompt.ilike(like))
        elif cat == "host":
            query = query.filter(LogRecord.host.ilike(like))
        elif cat == "pc_name":
            query = query.filter(LogRecord.hostname.ilike(like))
        elif cat == "public_ip":
            query = query.filter(LogRecord.public_ip.ilike(like))
        elif cat == "private_ip":
            query = query.filter(LogRecord.private_ip.ilike(like))
        elif cat == "entity":
            # entities(JSON) 문자열 검색
            query = query.filter(cast(LogRecord.entities, Text).ilike(like))
        else:
            # 카테고리 없으면 여러 컬럼 OR 검색
            query = query.filter(
                (LogRecord.prompt.ilike(like))
                | (LogRecord.host.ilike(like))
                | (LogRecord.hostname.ilike(like))
                | (LogRecord.public_ip.ilike(like))
                | (LogRecord.private_ip.ilike(like))
            )

    query = query.order_by(LogRecord.created_at.desc())

    total = query.count()
    rows: List[LogRecord] = (
        query.offset((page - 1) * page_size).limit(page_size).all()
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append({
            "id": getattr(r, "request_id", None),
            "prompt": r.prompt,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "time": r.created_at.isoformat() if r.created_at else None,
            "host": r.host,
            "hostname": r.hostname,
            "public_ip": r.public_ip,
            "internal_ip": r.private_ip,            # 프론트에서는 Internal IP/Private IP 컬럼으로 사용
            "interface": r.interface,
            "action": r.action,
            "allow": r.allow,
            "has_sensitive": r.has_sensitive,
            "file_blocked": r.file_blocked,
            "entities": r.entities or [],
            "reason": getattr(r, "reason", None),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/mcp/config_summary")
def mcp_config_summary(db: Session = Depends(get_db)):
    """
    MCP 설정 파일 기반 CONFIG 리포트 요약

    - active_total: 현재 활성화된 MCP 서버 개수
    - active_rank: MCP 이름별 활성 개수 순위
    - type_distribution: local / external / other 비율
    - timeline: 최근 스냅샷 기준 등록/변경/삭제 타임라인
    - prediction: 정규표현식을 이용한 URL 기반 악성 징후 진단 결과
    """

    # ---- 1) 현재 활성 스냅샷 (pc_name+host+file_path 별 최신) ----
    latest_sub = (
        db.query(
            McpConfigEntry.pc_name.label("pc_name"),
            McpConfigEntry.host.label("host"),
            McpConfigEntry.file_path.label("file_path"),
            func.max(McpConfigEntry.agent_time).label("max_time"),
        )
        .group_by(
            McpConfigEntry.pc_name,
            McpConfigEntry.host,
            McpConfigEntry.file_path,
        )
        .subquery()
    )

    current_entries: List[McpConfigEntry] = (
        db.query(McpConfigEntry)
        .join(
            latest_sub,
            (McpConfigEntry.pc_name == latest_sub.c.pc_name)
            & (McpConfigEntry.host == latest_sub.c.host)
            & (McpConfigEntry.file_path == latest_sub.c.file_path)
            & (McpConfigEntry.agent_time == latest_sub.c.max_time),
        )
        .filter(func.lower(McpConfigEntry.status) != "delete")
        .all()
    )

    # ---- 2) 활성 MCP 개수 / 순위 / 타입 분포 ----
    active_total = sum(1 for e in current_entries if e.mcp_name)

    rank_counts: Dict[str, int] = {}
    type_dist = {"local": 0, "external": 0, "other": 0}

    for e in current_entries:
        name = (e.mcp_name or "UNKNOWN").strip() or "UNKNOWN"
        rank_counts[name] = rank_counts.get(name, 0) + 1

        scope = (e.mcp_scope or "").lower()
        if scope == "local":
            type_dist["local"] += 1
        elif scope == "external":
            type_dist["external"] += 1
        else:
            type_dist["other"] += 1

    active_rank = [
        {"mcp_name": name, "count": count}
        for name, count in sorted(
            rank_counts.items(), key=lambda kv: kv[1], reverse=True
        )
    ]

    # ---- 3) 최근 스냅샷 기반 타임라인 ----
    # snapshot_id 별 최신 시간만 뽑아서 50개 제한
    snap_rows = (
        db.query(
            McpConfigEntry.snapshot_id,
            func.max(McpConfigEntry.agent_time).label("agent_time"),
        )
        .group_by(McpConfigEntry.snapshot_id)
        .order_by(func.max(McpConfigEntry.agent_time).desc())
        .limit(50)
        .all()
    )

    snap_ids = [r.snapshot_id for r in snap_rows]
    timeline: List[Dict[str, Any]] = []

    if snap_ids:
        all_snap_entries: List[McpConfigEntry] = (
            db.query(McpConfigEntry)
            .filter(McpConfigEntry.snapshot_id.in_(snap_ids))
            .all()
        )

        # snapshot_id -> 메타 + 엔트리 목록
        snaps: Dict[str, Dict[str, Any]] = {}
        for e in all_snap_entries:
            s = snaps.setdefault(
                e.snapshot_id,
                {
                    "agent_time": e.agent_time,
                    "pc_name": e.pc_name,
                    "private_ip": e.private_ip,
                    "host": e.host,
                    "file_path": e.file_path,
                    "status": e.status,
                    "entries": [],
                },
            )
            s["entries"].append(e)

        # 등록/변경/삭제 판별용: pc_name+host+file_path 기준으로 과거 존재 여부 체크
        sorted_by_time = sorted(
            snaps.values(), key=lambda x: (x["agent_time"] or "")
        )
        seen_keys = set()
        for snap in sorted_by_time:
            key = (snap["pc_name"], snap["host"], snap["file_path"])
            st = (snap["status"] or "").lower()
            if st == "delete":
                event = "삭제"
            else:
                event = "등록" if key not in seen_keys else "변경"
            snap["event"] = event
            seen_keys.add(key)

        # 최신 순으로 10개만 타임라인에 노출
        latest_snaps = sorted(
            snaps.values(),
            key=lambda x: (x["agent_time"] or ""),
            reverse=True,
        )[:10]

        for snap in latest_snaps:
            entries = snap["entries"]
            names = sorted(
                {e.mcp_name for e in entries if e.mcp_name}
            )
            if not names:
                mcp_label = "-"
            elif len(names) == 1:
                mcp_label = names[0]
            else:
                mcp_label = f"{names[0]} 외 {len(names) - 1}개"

            scopes = { (e.mcp_scope or "").lower() for e in entries if e.mcp_scope }
            if "external" in scopes:
                type_label = "Remote"
            elif "local" in scopes:
                type_label = "Local"
            else:
                type_label = "기타"

            timeline.append(
                {
                    "time": snap["agent_time"],
                    "event": snap.get("event", ""),
                    "pc_name": snap["pc_name"],
                    "private_ip": snap["private_ip"],
                    "host": snap["host"],
                    "mcp": mcp_label,
                    "type": type_label,
                }
            )

    # ---- 4) 정규표현식 기반 악성 징후(PREDICTION) ----
    suspicious_entries: List[McpConfigEntry] = []
    for e in current_entries:
        url = (e.url or "").strip()
        if not url:
            continue
        if IP_URL_RE.search(url):
            suspicious_entries.append(e)

    if suspicious_entries:
        sus_mcp_names = sorted(
            { (e.mcp_name or "UNKNOWN") for e in suspicious_entries }
        )
        prediction = {
            "has_suspicious": True,
            "headline": "일부 MCP 서버 URL에서 직접 IP 기반 접속이 감지되었습니다.",
            "detail": (
                "현재 활성 MCP 중 "
                f"{len(sus_mcp_names)}개({', '.join(sus_mcp_names[:3])}"
                f"{' 등' if len(sus_mcp_names) > 3 else ''})의 URL이 "
                "https://IP 형태로 설정되어 있습니다. "
                "내부 테스트용이 아니라면, 도메인 기반 접속 및 서버 신뢰도 검토가 필요합니다."
            ),
        }
    else:
        prediction = {
            "has_suspicious": False,
            "headline": "현재 MCP 설정에서 명백한 악성 징후는 발견되지 않았습니다.",
            "detail": (
                "활성화된 MCP 서버들의 URL에서 직접 IP 기반 https 접속은 "
                "정규표현식 검사 기준으로 확인되지 않았습니다. "
                "현 시점에서는 기본 형식 상의 위험 요소는 낮은 편입니다."
            ),
        }

    return {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "active_total": active_total,
        "active_rank": active_rank,
        "type_distribution": type_dist,
        "timeline": timeline,
        "prediction": prediction,
    }

@router.get("/network/summary", dependencies=[Depends(require_admin)])
def network_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    네트워크 리포트(외부 IP / 사설망 / 의심 PC)용 요약 데이터.

    - public_band_usage: 공인 IP /16 대역별 사용 건수
    - public_band_count: 공인 IP 대역 개수 (PUBLIC 대역 개수 카드)
    - top_private_bands: 공인 IP 대역 기준 상위 3개 사설망 정보
    - suspicious_pcs: 외부 IP 사용 의심 PC 요약 (직접 노출 / 신규 출구)
    - suspicious_logs: 의심 PC 관련 로그 테이블용 레코드
    """

    # 모든 로그 (추후 기간 필터링이 필요하면 여기서 where 조건 추가)
    rows: List[LogRecord] = (
        db.query(LogRecord)
        .order_by(LogRecord.created_at.asc())
        .all()
    )

    # 1) 공인 IP 대역 사용 현황 (PUBLIC 대역)
    # key: "A.B.*"  (/16 대역)
    public_band_usage: Dict[str, int] = defaultdict(int)

    # 2) 공인 IP 대역별 연결 사설망 정보
    band_private_bands: Dict[str, set] = defaultdict(set)   # 사설망 /16 대역 집합
    band_pc_names: Dict[str, set] = defaultdict(set)        # 해당 대역 사용하는 PCName 집합
    band_sensitive_count: Dict[str, int] = defaultdict(int) # 중요정보 탐지 건수

    # 3) 외부 IP 사용 의심 PC 정보
    # key = (public_ip, private_ip, pc_name)
    suspicious_map: Dict[tuple, Dict[str, Any]] = {}

    # 4) 의심 로그 목록 (테이블용)
    suspicious_logs: List[Dict[str, Any]] = []

    for r in rows:
        pub = (r.public_ip or "").strip()
        priv = (r.private_ip or "").strip()
        pc_name = (r.hostname or "").strip() or "UNKNOWN"
        created = r.created_at
        created_str = created.isoformat() if created else (r.time or "")

        # ---------- 공인 IP 대역 집계 (PUBLIC 대역 개수 / 대역폭 사용 현황) ----------
        if pub:
            try:
                ip_obj = ipaddress.ip_address(pub)
                # 공인 IP만 대상 (사설/루프백 등은 제외)
                if ip_obj.is_global:
                    octets = pub.split(".")
                    if len(octets) == 4:
                        band = f"{octets[0]}.{octets[1]}.*"
                        public_band_usage[band] += 1

                        # 이 PUBLIC 대역을 사용하는 사설망 대역 목록 (PRIVATE IP 기준)
                        if priv:
                            try:
                                priv_obj = ipaddress.ip_address(priv)
                                if priv_obj.is_private:
                                    po = priv.split(".")
                                    if len(po) == 4:
                                        priv_band = f"{po[0]}.{po[1]}.*"
                                        band_private_bands[band].add(priv_band)
                            except ValueError:
                                pass

                        band_pc_names[band].add(pc_name)
                        if r.has_sensitive:
                            band_sensitive_count[band] += 1
            except ValueError:
                # 잘못된 IP 문자열은 무시
                pass

        # ---------- 외부 IP 사용 의심 PC 판별 ----------
        reason = None

        # (1) PUBLIC IP == PRIVATE IP  → 직접 인터넷 노출
        if pub and priv and pub == priv:
            reason = "direct_exposure"

        # (2) PRIVATE IP가 사설대역이 아님 → 신규 출구
        elif priv:
            try:
                priv_obj = ipaddress.ip_address(priv)
                if not priv_obj.is_private:
                    reason = "new_egress"
            except ValueError:
                # IP 형식이 아니면 무시
                pass

        if reason:
            key = (pub, priv, pc_name)
            prev = suspicious_map.get(key)
            # 같은 조합이면 더 최근 시간으로 갱신
            if not prev or prev["last_time"] < created_str:
                suspicious_map[key] = {
                    "public_ip": pub,
                    "private_ip": priv,
                    "pc_name": pc_name,
                    "reason": reason,        # "direct_exposure" or "new_egress"
                    "last_time": created_str,
                }

            # 이 로그도 "외부 IP 사용 의심 PC 로그" 테이블에 포함
            suspicious_logs.append({
                "time": created_str,
                "host": r.host,
                "pc_name": pc_name,
                "public_ip": pub,
                "private_ip": priv,
                "interface": r.interface,
                "action": r.action,
                "allow": r.allow,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "entities": r.entities or [],
                "prompt": (
                    (r.prompt[:120] + "…")
                    if r.prompt and len(r.prompt) > 120
                    else (r.prompt or "")
                ),
            })

    # ---------- 대역폭 별 연결 사설망 (상위 3개) ----------
    band_items: List[Dict[str, Any]] = []
    for band, cnt in public_band_usage.items():
        priv_bands = sorted(band_private_bands.get(band, []))
        band_items.append({
            "public_band": band,                         # 예: "221.111.*"
            "total_logs": cnt,                           # 이 PUBLIC 대역으로 나간 전체 로그 수
            "private_band_count": len(priv_bands),       # 연결된 사설망 /16 대역 수
            "private_bands": priv_bands,                 # ["192.168.*", "172.16.*", ...]
            "pc_count": len(band_pc_names.get(band, [])),
            "sensitive_count": band_sensitive_count.get(band, 0),
        })

    # 사용량 기준 내림차순 정렬 후 상위 3개만 카드용으로 사용
    top_private_bands = sorted(
        band_items, key=lambda x: x["total_logs"], reverse=True
    )[:3]

    # ---------- 외부 IP 사용 의심 PC 정보 (카드용) ----------
    suspicious_pcs = sorted(
        suspicious_map.values(),
        key=lambda x: x["last_time"],
        reverse=True,
    )[:20]  # 카드에는 최대 20개만

    # 로그 테이블도 최신순 50개로 제한
    suspicious_logs = sorted(
        suspicious_logs,
        key=lambda x: x["time"],
        reverse=True,
    )[:50]

    return {
        # PUBLIC 대역 개수 카드 + PUBLIC 대역 파이 차트
        "public_band_usage": dict(public_band_usage),   # { "221.111.*": 10, ... }
        "public_band_count": len(public_band_usage),    # 예: 12

        # 대역폭 별 연결 사설망 (상위 3개 카드)
        "top_private_bands": top_private_bands,

        # 외부 IP 사용 의심 PC 정보 카드
        #  - 각 원소: {public_ip, private_ip, pc_name, reason("direct_exposure"/"new_egress"), last_time}
        "suspicious_pcs": suspicious_pcs,

        # 외부 IP 사용 의심 PC 로그 테이블
        "suspicious_logs": suspicious_logs,
    }

@router.get("/report/llm/file-summary", dependencies=[Depends(require_admin)])
def report_llm_file_summary(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    LLM 인터페이스 중 파일(attachment)이 있는 로그만 대상으로
    - 확장자별 개수 (도넛 차트용)
    - 확장자 x 라벨별 개수 (스택 바용)
    - 최근 20건 테이블
    을 반환
    """

    # 1) 파일 첨부된 LLM 로그만 조회 (interface 소문자 기준으로 필터)
    q = (
        db.query(LogRecord)
        .filter(func.lower(LogRecord.interface) == "llm")
        .filter(LogRecord.attachment.isnot(None))  # SQLite: IS NOT NULL
        .order_by(LogRecord.created_at.desc())
    )

    rows: List[LogRecord] = q.limit(200).all()

    # 2) 도넛: 확장자별 개수
    donut_counts: Dict[str, int] = defaultdict(int)

    # 3) 스택 바: 확장자 x 라벨
    stacked_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # 4) 테이블: 최근 20건
    recent: List[Dict[str, Any]] = []

    for r in rows:
        # --- attachment 파싱 (TEXT/JSON → dict 통일) ---
        att = _parse_attachment(r.attachment)
        ext = (att.get("format") or "unknown").strip().lower()

        # 도넛 카운트
        donut_counts[ext] += 1

        # 엔티티 라벨 집계
        for e in (r.entities or []):
            lab = (e.get("label") or "OTHER").upper()
            stacked_counts[ext][lab] += 1

        # 최근 20건 테이블
        if len(recent) < 20:
            recent.append(
                {
                    "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                    "host": r.host,
                    "pc_name": r.hostname,   # PC 이름
                    "public_ip": r.public_ip,
                    "private_ip": r.private_ip,
                    "action": r.action,
                    "has_sensitive": r.has_sensitive,
                    "file_blocked": r.file_blocked,
                    "file_ext": ext,
                }
            )

    # 차트용 구조 정리
    ext_labels = sorted(donut_counts.keys())
    donut_data = [donut_counts[e] for e in ext_labels]

    all_entity_labels = sorted(
        {lab for ext_map in stacked_counts.values() for lab in ext_map.keys()}
    )

    matrix: List[List[int]] = []
    for ext in ext_labels:
        row = [stacked_counts[ext].get(lab, 0) for lab in all_entity_labels]
        matrix.append(row)

    return {
        "donut": {
            "labels": ext_labels,
            "data": donut_data,
        },
        "stacked": {
            "formats": ext_labels,
            "labels": all_entity_labels,
            "matrix": matrix,
        },
        "recent": recent,
    }

# ---------- Reason 페이지: 탐지 건수 TOP 5 ----------

@router.get("/reason/top5", dependencies=[Depends(require_admin)])
def reason_top5(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Reason 페이지 상단 '탐지 건수 TOP 5'용 데이터.
    - has_sensitive=True 인 로그만 대상으로
      host + hostname(PC Name) 기준 탐지 건수 TOP5.
    """
    cnt_expr = func.count(LogRecord.request_id)

    rows = (
        db.query(
            LogRecord.hostname.label("pc_name"),
            LogRecord.host.label("host"),
            LogRecord.public_ip.label("public_ip"),
            LogRecord.private_ip.label("private_ip"),
            cnt_expr.label("count"),
        )
        .filter(LogRecord.has_sensitive.is_(True))
        .group_by(
            LogRecord.hostname,
            LogRecord.host,
            LogRecord.public_ip,
            LogRecord.private_ip,
        )
        .order_by(cnt_expr.desc())
        .limit(5)
        .all()
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "pc_name": r.pc_name or "UNKNOWN",
                "host": r.host,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "count": r.count,
            }
        )

    return {"items": items}


# ---------- Reason 페이지: 선택된 PC 상세 분석 ----------

@router.get("/reason/summary", dependencies=[Depends(require_admin)])
def reason_summary(
    pc_name: str,
    host: str | None = None,
    interface: str | None = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    특정 PC (hostname 기준)에 대해:
    - 중요정보 탐지 로그 목록
    - 각 로그의 위험 카테고리/패턴/설명
    - 간단한 의도성(고의/부주의) 판단 및 Reason 한 줄
    을 반환.

    (현재 intent 판단은 휴리스틱/로컬 LLM 기반이며,
     향후 고도화 가능)
    """
    if not pc_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pc_name is required",
        )

    q = db.query(LogRecord).filter(LogRecord.has_sensitive.is_(True))
    q = q.filter(LogRecord.hostname == pc_name)

    if host:
        q = q.filter(LogRecord.host == host)
    if interface:
        q = q.filter(func.lower(LogRecord.interface) == interface.lower())

    logs: List[LogRecord] = q.order_by(LogRecord.created_at.asc()).all()

    if not logs:
        return {
            "pc_name": pc_name,
            "host": host,
            "interface": interface,
            "log_count": 0,
            "overall_result": "",
            "investigate_users": 0,
            "educate_users": 0,
            "intent_rate": 0.0,
            "intent_counts": {"intentional": 0, "negligent": 0, "unknown": 0},
            "risk_category_counts": {},
            "cards": [],
            "logs": [],
        }

    intent_counts: Counter[str] = Counter()
    risk_category_counts: Counter[str] = Counter()

    cards: List[Dict[str, Any]] = []
    table_rows: List[Dict[str, Any]] = []

    for idx, r in enumerate(logs):
        entities = r.entities or []
        risk_info = classify_risk_from_entities(entities)

        # 최근 5개 + 현재 로그까지 컨텍스트
        start = max(0, idx - 5)
        context_logs = logs[start : idx + 1]

        #intent_type, reason_text = infer_intent_and_reason_from_context(
        #    context_logs, risk_info
        #)

        # 로컬 LLM 판단으로 변경
        intent_type, reason_text = infer_intent_with_llm(context_logs, risk_info)

        # None 등은 전부 unknown으로 정규화
        if intent_type not in ("intentional", "negligent", "unknown"):
            intent_type = "unknown"

        intent_counts[intent_type] += 1
        risk_category_counts[risk_info["category"]] += 1

        # 위험 콤보 라벨 (캐러셀용)
        combo_labels = detect_combo_labels(entities)

        # DB 컬럼이 있으면 저장 (없으면 조용히 무시)
        if hasattr(r, "reason"):
            r.reason = reason_text
        if hasattr(r, "reason_type"):
            r.reason_type = intent_type
        if hasattr(r, "risk_category"):
            r.risk_category = risk_info["category"]
        if hasattr(r, "risk_pattern"):
            r.risk_pattern = risk_info["pattern"]

        # 카드용 (프롬프트 위험 분석 결과)
        cards.append(
            {
                "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                "host": r.host,
                "pc_name": r.hostname,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "prompt": (
                    (r.prompt[:240] + "…")
                    if r.prompt and len(r.prompt) > 240
                    else (r.prompt or "")
                ),
                "entities": [
                    {"label": (e.get("label") or ""), "value": e.get("value")}
                    for e in entities
                ],
                "risk_category": risk_info["category"],
                "risk_pattern": risk_info["pattern"],
                "risk_description": risk_info["description"],
                "intent_type": intent_type,
                "reason": reason_text,
                "combo_labels": combo_labels,
            }
        )

        # 하단 테이블용 (그래프 계산 위해 entities 포함)
        table_rows.append(
            {
                "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                "host": r.host,
                "pc_name": r.hostname,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "reason": reason_text,
                "reason_type": intent_type,
                "risk_category": risk_info["category"],
                "entities": entities,
            }
        )

    # 의도성 통계 → 종합 분석 결과용 숫자/문구 생성
    intentional = intent_counts.get("intentional", 0)
    negligent = intent_counts.get("negligent", 0)
    unknown = intent_counts.get("unknown", 0)
    total = intentional + negligent + unknown

    if total > 0:
        intent_rate = (intentional / total) * 100.0
    else:
        intent_rate = 0.0

    overall_result = f"조사 필요 {intentional}건, 교육 필요 {negligent}건"

    # 여기서는 '조사 필요 사용자/교육 필요 사용자'를
    # 일단 건수 기준으로 그대로 사용 (원하면 향후 사용자 단위로 변경 가능)
    investigate_users = intentional
    educate_users = negligent

    # 필요하다면 여기서 db.commit() 호출 (세션 정책에 따라)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # 실패하더라도 조회용 API라서 그대로 반환은 가능

    return {
        "pc_name": pc_name,
        "host": host,
        "interface": interface,
        "log_count": len(logs),
        "overall_result": overall_result,
        "investigate_users": investigate_users,
        "educate_users": educate_users,
        "intent_rate": intent_rate,
        "intent_counts": {
            "intentional": intentional,
            "negligent": negligent,
            "unknown": unknown,
        },
        "risk_category_counts": dict(risk_category_counts),
        "cards": cards,
        "logs": table_rows,
    }
