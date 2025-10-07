# app.py
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routers.logs import router as logs_router
from routers.dashboard_api import router as dashboard_router

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"

app = FastAPI(title="Sentinel Solution Server", version="2.1.0")

# 정적 파일: /dashboard/static/*
app.mount("/dashboard/static", StaticFiles(directory=DASHBOARD_DIR), name="dashboard-static")

# 라우터
app.include_router(logs_router)
app.include_router(dashboard_router)

# 보안 헤더(클릭재킹/스니핑/XSS 완화)
@app.middleware("http")
async def security_headers(req: Request, call_next):
    resp: Response = await call_next(req)
    # 프레임 금지(클릭재킹 방지)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    # MIME 스니핑 방지
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    # 리퍼러 최소화
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    # CSP: 현재 개발 단계 — CDN 사용 + 인라인 스타일 임시 허용
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "  # ← inline style 허용(임시)
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "                # ← jsdelivr sourcemap 허용
        "frame-ancestors 'none'"
    )
    # HSTS: 신뢰 인증서로 HTTPS 안정화 후 주석 해제 권장
    # resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
    return resp
