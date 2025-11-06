# app.py
from __future__ import annotations
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routers.logs import router as logs_router
from routers.dashboard_api import router as dashboard_router

# (AI) 서버 부팅 시 모델 선로딩
from services.ai_detector import init_from_env

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"          # 빌드 산출물(index.html, assets/*)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # AI 감지기: USE_AI_DETECTOR=true면 부팅 시 1회 로드 (GPU 고정 실패 시 경고만)
    if os.getenv("USE_AI_DETECTOR", "true").lower() in ("1", "true", "yes"):
        try:
            init_from_env()
            print("[INFO] AI detector initialized from env (MODEL_DIR, MAX_NEW_TOKENS).")
        except Exception as e:
            # 서버는 뜨되, 탐지는 안전폴백(빈 결과)로 동작
            print(f"[WARN] AI detector init failed: {e!r}")
    yield
    # teardown 없음

app = FastAPI(
    title="Sentinel Solution Server",
    version="2.2.0",
    lifespan=lifespan,
)

# ---------------------------
# 정적/대시보드 (SPA)
# ---------------------------
# 1) /dashboard 에 정적 자산+index.html 서빙
#    - html=True 로 index.html 자동 서빙
app.mount(
    "/dashboard",
    StaticFiles(directory=DASHBOARD_DIR, html=True),
    name="dashboard",
)

# 2) SPA 딥링크 폴백:
#    /dashboard/* 로 직접 접근 시 index.html 반환 (StaticFiles(html=True)로 대부분 커버되지만 보강)
@app.get("/dashboard/{path:path}")
async def dashboard_fallback(path: str):
    index_file = DASHBOARD_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return Response(status_code=404, content="dashboard not found")

# ---------------------------
# API 라우터
# ---------------------------
app.include_router(logs_router)
app.include_router(dashboard_router)

# ---------------------------
# 보안 헤더(클릭재킹/스니핑/XSS 완화)
# ---------------------------
@app.middleware("http")
async def security_headers(req: Request, call_next):
    resp: Response = await call_next(req)
    # 클릭재킹 방지
    resp.headers.setdefault("X-Frame-Options", "DENY")
    # MIME 스니핑 방지
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    # 최소 리퍼러
    resp.headers.setdefault("Referrer-Policy", "no-referrer")

    # CSP: 동일 오리진 + (필요시 CDN 허용). 대시보드가 CDN을 쓴다면 주석 해제.
    cdn = " https://cdn.jsdelivr.net"
    # cdn = ""  # CDN 미사용 기본
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        f"script-src 'self'{cdn}; "
        f"style-src 'self' 'unsafe-inline'{cdn}; "
        "img-src 'self' data:; "
        "connect-src 'self'; "   # 대시보드에서 동일 오리진 API 호출
        "frame-ancestors 'none'"
    )

    # HSTS: 신뢰 인증서(Let's Encrypt) 적용 후 활성화 권장
    # resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
    return resp
