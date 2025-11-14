# routers/dashboard_api.py
from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import cast, Text  # ★ entities 검색용

from db import SessionLocal, Base, engine
from models import LogRecord
from config import settings

router = APIRouter()  # 접두는 app.py에서 prefix="/api"로 부여

# 운영에서는 Alembic 권장. 개발 편의를 위해 안전 생성.
Base.metadata.create_all(bind=engine)

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

# ---------- 요약 API ----------
@router.get("/summary", dependencies=[Depends(require_admin)])
def dashboard_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    대시보드 요약 데이터:
    - total_sensitive: has_sensitive=True 총 건수 (탐지 총합)
    - total_blocked: 차단된 요청 수 (allow=False 또는 action startswith("block"))
    - type_ratio: 라벨 비율(엔티티 라벨 카운트, 전체 기간)
    - type_detected: 유형별 탐지 횟수(전체 기간)
    - type_blocked: 유형별 차단 횟수(파일 유사 차단은 FILE_SIMILAR)
    - hourly_attempts: 0~23시 카운트(모든 요청, 전체 기간)
    - hourly_type: 시간대별(0~23) · 라벨별 탐지 건수 (has_sensitive=True)
    - recent_logs: 최근 20건 (민감값 미노출)

    - today_sensitive: 오늘 탐지된 건수 (has_sensitive=True)
    - today_blocked: 오늘 차단된 요청 수
    - today_hourly: 오늘 시간대별 탐지 건수 [0..23]
    - today_type_ratio: 오늘 탐지된 라벨 비율
    - ip_band_detected: 공인IP /16 대역별 탐지 건수 (has_sensitive=True, 전체 기간)
    - ip_band_blocked: 공인IP /16 대역별 차단 건수 (전체 기간)
    """
    rows: List[LogRecord] = (
        db.query(LogRecord).order_by(LogRecord.created_at.desc()).all()
    )

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
        # created_at 이 None인 경우를 대비
        created_date: date | None = created.date() if created else None
        hour: int | None = created.hour if created else None

        # === 공통: 시간대별 "시도" 카운트 (모든 요청) ===
        if hour is not None and 0 <= hour < 24:
            try:
                hourly_attempts[hour] += 1
            except Exception:
                pass

        # === 탐지 관련 집계 ===
        if r.has_sensitive:
            total_sensitive += 1

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

        # === 차단 관련 집계(기존 로직 유지) ===
        action = (r.action or "")
        is_blocked = (r.allow is False) or action.startswith("block")

        if is_blocked:
            total_blocked += 1
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
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "entities": [{"label": (e.get("label") or "")} for e in (r.entities or [])],
                "prompt": (r.prompt[:120] + "…") if r.prompt and len(r.prompt) > 120 else (r.prompt or ""),
            })

    # hourly_type 은 {시간(int): {라벨:카운트}} → JSON 직렬화 위해 키를 문자열로
    hourly_type_serialized: Dict[str, Dict[str, int]] = {
        str(h): dict(type_counts) for h, type_counts in hourly_type.items()
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
    - page_size: 페이지 크기 (최대 100)
    - q: 검색 키워드
    - category: 검색 대상 컬럼
      - prompt | host | pc_name | public_ip | private_ip | entity
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

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
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
