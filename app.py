# app.py
from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from routers.logs import router as logs_router
from routers.dashboard_api import router as dashboard_router
from routers.mcp import router as mcp_router  # MCP 설정 전용 라우터 추가

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"  # index.html, app.js, vendor/*

# 선로딩 제거: 서버 시작 시 모델을 올리지 않음 (요청 시 외부 판별기 호출)
app = FastAPI(
    title="Sentinel Solution Server",
    version="2.2.0",
)

# ---------- 정적/대시보드 (SPA) ----------
# /dashboard 경로에 정적 자산 + index.html 자동 서빙
app.mount(
    "/dashboard",
    StaticFiles(directory=DASHBOARD_DIR, html=True),
    name="dashboard",
)

# ---------- API 라우터 ----------
# ★ 핵심: API는 /api 로 분리 (정적과 충돌 방지)
app.include_router(logs_router,      prefix="/api")
app.include_router(mcp_router,       prefix="/api")  # ✅ /api/mcp 엔드포인트 등록
app.include_router(dashboard_router, prefix="/api")

# ---------- 보안 헤더 ----------
@app.middleware("http")
async def security_headers(req: Request, call_next):
    resp: Response = await call_next(req)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")

    # CDN(jsdelivr) 허용. API는 동일 오리진(/api)만 호출
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "frame-ancestors 'none'"
    )
    # 신뢰 인증서 안정화 후 HSTS 활성 권장:
    # resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
    return resp
