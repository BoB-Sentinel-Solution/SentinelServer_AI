# -*- coding: utf-8 -*-
from fastapi import FastAPI
from .logger_router import router as log_router

app = FastAPI(title="Sentinel Logger (mTLS)", version="1.0.0")
app.include_router(log_router)
