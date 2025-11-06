# routers/dashboard_api.py
from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

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
    - total_sensitive: has_sensitive=True 총 건수
    - type_ratio: 라벨 비율(엔티티 라벨 카운트)
    - type_blocked: 유형별 차단 횟수(파일 유사 차단은 FILE_SIMILAR)
    - hourly_attempts: 0~23시 카운트
    - recent_logs: 최근 20건 (민감값 미노출)
    - ip_band_blocked: 공인IP /16 대역별 차단 건수 (e.g., '203.0.*')
    """
    rows: List[LogRecord] = db.query(LogRecord).order_by(LogRecord.created_at.desc()).all()

    total_sensitive = 0
    type_ratio: Dict[str, int] = defaultdict(int)
    type_blocked: Dict[str, int] = defaultdict(int)
    hourly_attempts = [0] * 24
    recent_logs: List[Dict[str, Any]] = []
    ip_band_blocked: Dict[str, int] = defaultdict(int)

    for r in rows:
        # 중요정보 탐지 건수 / 비율
        if r.has_sensitive:
            total_sensitive += 1
            for e in (r.entities or []):
                type_ratio[e.get("label", "OTHER")] += 1

        # 차단 집계
        action = (r.action or "")
        if (r.allow is False) or action.startswith("block"):
            if r.entities:
                for e in r.entities:
                    type_blocked[e.get("label", "OTHER")] += 1
            if r.file_blocked and not r.entities:
                type_blocked["FILE_SIMILAR"] += 1

            if r.public_ip and r.public_ip.count(".") == 3:
                a, b, *_ = r.public_ip.split(".")
                ip_band_blocked[f"{a}.{b}.*"] += 1

        # 시간대별 입력 시도 (모든 요청)
        if r.created_at:
            try:
                hourly_attempts[r.created_at.hour] += 1
            except Exception:
                pass

        # 최근 로그 20건 (민감값 미노출)
        if len(recent_logs) < 20:
            recent_logs.append({
                "time": r.created_at.isoformat() if r.created_at else r.time,
                "host": r.host,
                "hostname": r.hostname,
                "public_ip": r.public_ip,
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "entities": [{"label": (e.get("label") or "")} for e in (r.entities or [])],
                "prompt": (r.prompt[:120] + "…") if r.prompt and len(r.prompt) > 120 else (r.prompt or ""),
            })

    return {
        "total_sensitive": total_sensitive,
        "type_ratio": dict(type_ratio),
        "type_blocked": dict(type_blocked),
        "hourly_attempts": hourly_attempts,
        "recent_logs": recent_logs,
        "ip_band_blocked": dict(ip_band_blocked),
    }
