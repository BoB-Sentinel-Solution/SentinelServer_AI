# schemas.py
from typing import Optional, List
from pydantic import BaseModel, Field

# === Agent -> Server (요청) ===
class Attachment(BaseModel):
    format: Optional[str] = None   # 예: "image/png" | null
    data: Optional[str] = None     # base64 | null

class InItem(BaseModel):
    time: str
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    host: Optional[str] = None
    hostname: Optional[str] = None
    prompt: str
    attachment: Optional[Attachment] = None
    interface: str = "llm"

# === Server -> Agent (응답) ===
class Entity(BaseModel):
    value: str
    begin: int
    end: int
    label: str

class ServerOut(BaseModel):
    request_id: str
    host: str
    modified_prompt: str
    has_sensitive: bool
    entities: List[Entity] = Field(default_factory=list)
    processing_ms: int
    file_blocked: bool = False
    allow: bool = True
    action: str = "allow"
