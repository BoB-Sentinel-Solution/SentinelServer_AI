# app.py
from fastapi import FastAPI
from routers.logs import router as logs_router

app = FastAPI(title="Sentinel Solution Server", version="1.5.0")
app.include_router(logs_router)
