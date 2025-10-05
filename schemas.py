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
    host: Optional[str] = None           # 실제 LLM 대상 호스트 (예: chatgpt.com)
    hostname: Optional[str] = None       # 에이전트 PC 호스트명
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

    # 파일 제어 추가
    file_blocked: bool = False   # 첨부 민감 시 업로드 차단
    allow: bool = True           # 최종 허용 여부
    action: str = "allow"        # "allow" | "mask_and_allow" | "block_upload"
