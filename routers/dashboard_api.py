# routers/dashboard_api.py
from __future__ import annotations
from fastapi import APIRouter, Depends, Header, HTTPException, status  # 추가
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime

from db import SessionLocal, Base, engine
from models import LogRecord
from config import settings  # 추가

BASE_DIR = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = BASE_DIR / "dashboard"

router = APIRouter()

# 안전하게 테이블 생성(운영은 Alembic 권장)
Base.metadata.create_all(bind=engine)

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

# 대시보드 API 보호: .env에 DASHBOARD_API_KEY 설정 시에만 검사
def require_admin(x_admin_key: str | None = Header(default=None)):
    """
    - 설정에 DASHBOARD_API_KEY가 비어있지 않으면, 요청 헤더 X-Admin-Key 검증
    - 비어있다면(설정 안했으면) 기존과 동일하게 무인증 허용
    """
    if settings.DASHBOARD_API_KEY:
        if x_admin_key != settings.DASHBOARD_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

@router.get("/dashboard/")
def dashboard_index():
    """ /dashboard/ → 정적 index.html """
    index = DASHBOARD_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"error": "dashboard not installed"}, status_code=404)
    return FileResponse(index)

@router.get("/dashboard")
def dashboard_redirect_root():
    """ /dashboard → /dashboard/ 로 정규화 """
    return RedirectResponse(url="/dashboard/")

@router.get("/dashboard/api/summary", dependencies=[Depends(require_admin)])  # API 키 요구
def dashboard_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    대시보드 데이터 한 번에 제공
    - total_sensitive: 중요정보 탐지 총 건수(has_sensitive=True)
    - type_ratio: 엔티티 라벨 비율(EMAIL, PHONE, PASSWORD, USERNAME, CARD_NO, 기타)
    - type_blocked: 유형별 차단 횟수(파일유사 차단은 FILE_SIMILAR로 집계)
    - hourly_attempts: 0~23시 장바구니 (한국시간 기준 가정: created_at 로컬)
    - recent_logs: 최근 20건
    - ip_band_blocked: 공인IP /16 대역별 차단 건수 (예: '203.0.*')
    """
    # 최근 N만 가져와도 충분하지만, 우선 전체 스캔(데이터 커지면 기간 필터 추가)
    rows: List[LogRecord] = db.query(LogRecord).order_by(LogRecord.created_at.desc()).all()

    total_sensitive = 0
    type_ratio: Dict[str, int] = defaultdict(int)
    type_blocked: Dict[str, int] = defaultdict(int)
    hourly_attempts = [0] * 24
    recent_logs: List[Dict[str, Any]] = []
    ip_band_blocked: Dict[str, int] = defaultdict(int)

    for i, r in enumerate(rows):
        # 총 중요정보 탐지 건수
        if r.has_sensitive:
            total_sensitive += 1
            # 엔티티 비율
            for e in (r.entities or []):
                label = e.get("label", "OTHER")
                type_ratio[label] += 1

        # 차단 집계
        if not r.allow or (r.action or "").startswith("block"):
            # 엔티티 기반 차단
            if r.entities:
                for e in r.entities:
                    type_blocked[e.get("label", "OTHER")] += 1
            # 파일 유사도 차단 등 엔티티가 없을 수 있음
            if r.file_blocked and not r.entities:
                type_blocked["FILE_SIMILAR"] += 1

            # IP 대역(/16 느낌으로 단순화: 앞 2옥텟만)
            if r.public_ip and r.public_ip.count(".") == 3:
                parts = r.public_ip.split(".")
                band = f"{parts[0]}.{parts[1]}.*"
                ip_band_blocked[band] += 1

        # 시간대별 입력 시도 (모든 요청 기준)
        if r.created_at:
            try:
                hour = r.created_at.hour
                hourly_attempts[hour] += 1
            except Exception:
                pass

        # 최근 로그 20건  XSS 완화: 민감값(value) 미노출, 레이블만 보여줌
        if len(recent_logs) < 20:
            recent_logs.append({
                "time": r.created_at.isoformat() if r.created_at else r.time,
                "host": r.host,
                "hostname": r.hostname,
                "public_ip": r.public_ip,
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                # 엔티티는 label만 노출(값/인덱스 제거)
                "entities": [{"label": (e.get("label") or "")} for e in (r.entities or [])],
                # 프롬프트는 서버에서 120자 미리보기만 전달(프론트는 textContent로 렌더)
                "prompt": (r.prompt[:120] + "…") if r.prompt and len(r.prompt) > 120 else (r.prompt or ""),
            })

    # 프론트가 보기 쉽게 dict 변환 (Starlette/JSON 직렬화 일관성)
    resp = {
        "total_sensitive": total_sensitive,
        "type_ratio": dict(type_ratio),
        "type_blocked": dict(type_blocked),
        "hourly_attempts": hourly_attempts,
        "recent_logs": recent_logs,
        "ip_band_blocked": dict(ip_band_blocked),
    }
    return resp
