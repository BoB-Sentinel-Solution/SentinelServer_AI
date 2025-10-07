# routers/dashboard_api.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from db import SessionLocal, Base, engine
from models import LogRecord
from config import settings

BASE_DIR = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = BASE_DIR / "dashboard"

router = APIRouter()

# 안전하게 테이블 생성(운영은 Alembic 권장)
Base.metadata.create_all(bind=engine)


# --- DB DI -----------------------------------------------------------
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


# --- 인증(선택) ------------------------------------------------------
def require_admin(x_admin_key: str | None = Header(default=None)):
    """
    - .env의 DASHBOARD_API_KEY 가 설정되어 있으면 X-Admin-Key 헤더 검증
    - 미설정이면 무인증 허용(기존과 동일)
    """
    if settings.DASHBOARD_API_KEY:
        if x_admin_key != settings.DASHBOARD_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )


# --- 정적 페이지 -----------------------------------------------------
# HEAD 허용
@router.api_route("/dashboard/", methods=["GET", "HEAD"])
def dashboard_index():
    """ /dashboard/ → 정적 index.html """
    index = DASHBOARD_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"error": "dashboard not installed"}, status_code=404)
    return FileResponse(index)


# HEAD 허용
@router.api_route("/dashboard", methods=["GET", "HEAD"])
def dashboard_redirect_root():
    """ /dashboard → /dashboard/ 로 정규화 """
    return RedirectResponse(url="/dashboard/")


# --- 요약 API --------------------------------------------------------
@router.get("/dashboard/api/summary", dependencies=[Depends(require_admin)])
def dashboard_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    대시보드 데이터 한 번에 제공
    - total_sensitive: 중요정보 탐지 총 건수(has_sensitive=True)
    - type_ratio: 엔티티 라벨 비율(EMAIL, PHONE, PASSWORD, USERNAME, CARD_NO, 기타)
    - type_blocked: 유형별 차단 횟수(파일유사 차단은 FILE_SIMILAR로 집계)
    - hourly_attempts: 0~23시 장바구니
    - recent_logs: 최근 20건 (XSS 완화 위해 엔티티 value 미노출)
    - ip_band_blocked: 공인IP /16 대역별 차단 건수 (예: '203.0.*')
    """
    rows: List[LogRecord] = (
        db.query(LogRecord).order_by(LogRecord.created_at.desc()).all()
    )

    total_sensitive = 0
    type_ratio: Dict[str, int] = defaultdict(int)
    type_blocked: Dict[str, int] = defaultdict(int)
    hourly_attempts = [0] * 24
    recent_logs: List[Dict[str, Any]] = []
    ip_band_blocked: Dict[str, int] = defaultdict(int)

    for r in rows:
        # 총 중요정보 탐지 건수/비율
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

        # 최근 로그 20건 (민감값(value) 미노출, label만)
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
