# models.py
from sqlalchemy import Column, String, Boolean, Integer, DateTime, JSON, Text
from sqlalchemy.sql import func
from db import Base
from datetime import datetime

class LogRecord(Base):
    """
    한 레코드 = 에이전트 요청 + AI 판별 결과
    request_id (문자열 UUID) = PK
    """
    __tablename__ = "log_records"

    request_id      = Column(String(64), primary_key=True, index=True)

    # 원본(에이전트 요청)
    time            = Column(String, nullable=False)
    public_ip       = Column(String)
    private_ip      = Column(String)
    host            = Column(String)   # LLM 대상 호스트 (예: chatgpt.com)
    hostname        = Column(String)
    prompt          = Column(Text, nullable=False)
    attachment      = Column(JSON)     # {"format":..., "data":...} (운영에선 data 저장 지양)
    interface       = Column(String, default="llm")

    # 서버 결과
    modified_prompt = Column(Text, nullable=False)
    has_sensitive   = Column(Boolean, default=False, nullable=False)
    entities        = Column(JSON, default=list)   # [{"value","begin","end","label"}, ...]
    processing_ms   = Column(Integer, default=0, nullable=False)

    # 파일/정책
    file_blocked    = Column(Boolean, default=False, nullable=False)
    allow           = Column(Boolean, default=True,  nullable=False)
    action          = Column(String, default="allow")

    # 메타
    created_at      = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
