# app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routers.logs import router as logs_router
from routers.dashboard_api import router as dashboard_router  # ← 신규

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"

app = FastAPI(title="Sentinel Solution Server", version="2.0.0")

# 정적 파일 마운트: /dashboard/*  (index는 라우터에서 반환)
app.mount("/dashboard/static", StaticFiles(directory=DASHBOARD_DIR), name="dashboard-static")

# API 라우터들
app.include_router(logs_router)
app.include_router(dashboard_router)
