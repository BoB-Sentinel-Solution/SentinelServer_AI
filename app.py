from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class InItem(BaseModel):
    time: str
    host: str
    prompt: str
    interface: str

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/logs")
def ingest(item: InItem):
    # TODO: 중요정보 판별/마스킹 로직
    return {"action": "allow", "modified_prompt": item.prompt}