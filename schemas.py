from typing import Optional, List
from pydantic import BaseModel, Field

# === Agent -> Server ===
class Attachment(BaseModel):
    format: Optional[str] = None   # 예: "image/png", 없으면 None
    data: Optional[str] = None     # base64 문자열, 없으면 None

class InItem(BaseModel):
    time: str
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    host: Optional[str] = None
    hostname: Optional[str] = None
    prompt: str
    attachment: Optional[Attachment] = None
    interface: str = "llm"

# === Server -> Agent ===
class Entity(BaseModel):
    type: str
    value: str

class DetectResponse(BaseModel):
    has_sensitive: bool = False
    entities: List[Entity] = Field(default_factory=list)
    modified_prompt: str

# (옵션) 내부 디버깅/로그용
class OcrDebug(BaseModel):
    used: bool = False
    reason: Optional[str] = None
    chars: int = 0
