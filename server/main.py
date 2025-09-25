from fastapi import FastAPI
from .router_inspect import router as inspect_router

app = FastAPI(title="Sentinel Inspector (mTLS)", version="1.1.0")
app.include_router(inspect_router)
