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

    # 기존 호환: hostname 그대로 유지
    hostname: Optional[str] = None
    # 신규 허용: 에이전트가 보내는 PCName를 추가 (필드명은 pc_name, 입력 키는 'PCName')
    pc_name: Optional[str] = Field(default=None, alias="PCName")

    prompt: str
    attachment: Optional[Attachment] = None
    interface: str = "llm"

    # 별칭(PCName)로 들어와도 파싱되게
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

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
