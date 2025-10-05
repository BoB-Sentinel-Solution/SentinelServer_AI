from fastapi import FastAPI
from routers.logs import router as logs_router

def create_app() -> FastAPI:
    app = FastAPI(title="Sentinel Solution Server", version="1.1.0")
    app.include_router(logs_router)
    return app

app = create_app()
