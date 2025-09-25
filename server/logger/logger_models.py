# -*- coding: utf-8 -*-
import json, hashlib
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON as SA_JSON, select, Index
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from .logger_config import LOG_DATABASE_URL, KST, MAX_HEADERS_LEN, MAX_PREVIEW_BYTES

Base = declarative_base()
engine = create_async_engine(LOG_DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def take_preview(b: bytes, limit: int = MAX_PREVIEW_BYTES) -> str:
    if not b:
        return ""
    if len(b) <= limit:
        return b.decode("utf-8", errors="ignore")
    half = limit // 2
    head, tail = b[:half], b[-half:]
    return (head + b"\n…TRUNCATED…\n" + tail).decode("utf-8", errors="ignore")

def clamp_json_size(obj: Any, max_len: int = MAX_HEADERS_LEN) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        return None
    return obj if len(s) <= max_len else {"_truncated": True, "size": len(s)}

class LogEvent(Base):
    __tablename__ = "log_events"
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 메타
    time = Column(String(40), nullable=False)
    interface = Column(String(16), nullable=False)
    method = Column(String(8), nullable=False)
    scheme = Column(String(8), nullable=False)
    host = Column(String(255), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    path = Column(String(1024), nullable=False, index=True)
    query = Column(Text, nullable=True)
    client_ip = Column(String(64), nullable=True)
    tags = Column(SA_JSON, nullable=True)

    # 헤더(이미 에이전트에서 민감값 마스킹/단축됨)
    headers_redacted = Column(SA_JSON, nullable=True)

    # 본문: **원문 전문 저장 금지**
    body_sha256 = Column(String(64), nullable=True, index=True)
    body_preview = Column(Text, nullable=True)          # 원문 앞/뒤 일부
    body_masked_preview = Column(Text, nullable=True)   # 마스킹 결과 일부

    # 판정
    decision = Column(String(8), nullable=False)        # allow/mask/block
    reason = Column(String(64), nullable=False)
    rules_hit = Column(SA_JSON, nullable=True)
    masked = Column(Integer, nullable=False, default=0) # 0/1

    created_at = Column(DateTime(timezone=True), nullable=False, index=True)

Index("ix_log_events_host_path_time", LogEvent.host, LogEvent.path, LogEvent.created_at.desc())
