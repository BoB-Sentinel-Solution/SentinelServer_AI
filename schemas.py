# schemas.py
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel

class Attachment(BaseModel):
    format: Optional[str] = None   # MIME type (e.g., "image/png", "application/pdf")
    data:   Optional[str] = None   # base64 (운영에서는 저장 지양)

class InItem(BaseModel):
    time: str                      # ISO8601 or any string
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None

    host: Optional[str] = None     # 대상 서비스 호스트 (예: chatgpt.com)
    hostname: Optional[str] = None # 구 에이전트 필드
    pc_name: Optional[str] = None   # <- 에이전트가 보내는 PCName 수용

    prompt: str
    attachment: Optional[Attachment] = None
    interface: str = "llm"

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
    entities: List[Entity] = []
    processing_ms: int

    file_blocked: bool = False
    allow: bool = True
    action: str = "allow"
