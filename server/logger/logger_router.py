# -*- coding: utf-8 -*-
import base64
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from .logger_models import (
    AsyncSessionLocal, Base, engine, LogEvent, KST,
    take_preview, sha256_hex, clamp_json_size
)

router = APIRouter()

class InspectLikeIn(BaseModel):
    time: str
    interface: str
    method: str
    scheme: str
    host: str
    port: int
    path: str
    query: str = ""
    headers: Dict[str, Any] = Field(default_factory=dict)
    body_b64: Optional[str] = None
    client_ip: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    # 판정
    decision: str
    reason: str
    rules_hit: List[str] = Field(default_factory=list)
    masked_body_b64: Optional[str] = None

class LogOut(BaseModel):
    id: int
    time: str
    interface: str
    method: str
    scheme: str
    host: str
    port: int
    path: str
    query: Optional[str]
    client_ip: Optional[str]
    tags: List[str]
    decision: str
    reason: str
    rules_hit: List[str]
    body_sha256: Optional[str]
    body_preview: Optional[str]
    body_masked_preview: Optional[str]
    created_at: str

@router.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@router.get("/healthz")
async def healthz():
    return {"ok": True}

@router.post("/log")
async def log_event(inp: InspectLikeIn, request: Request):
    # 본문 복원 → 해시/미리보기만
    raw_body = b""
    if inp.body_b64:
        try:
            raw_body = base64.b64decode(inp.body_b64)
        except Exception:
            raw_body = b""

    masked_preview = ""
    if inp.masked_body_b64:
        try:
            masked_bytes = base64.b64decode(inp.masked_body_b64)
            masked_preview = take_preview(masked_bytes)
        except Exception:
            masked_preview = ""

    body_hash = sha256_hex(raw_body) if raw_body else None
    preview = take_preview(raw_body)
    headers_sanitized = clamp_json_size(inp.headers)

    evt = LogEvent(
        time=inp.time,
        interface=inp.interface.lower(),
        method=inp.method.upper(),
        scheme=inp.scheme.lower(),
        host=inp.host.lower(),
        port=inp.port,
        path=inp.path,
        query=inp.query or "",
        client_ip=inp.client_ip,
        tags=inp.tags or [],
        headers_redacted=headers_sanitized,
        body_sha256=body_hash,
        body_preview=preview,
        body_masked_preview=masked_preview or None,
        decision=inp.decision.lower(),
        reason=inp.reason,
        rules_hit=inp.rules_hit or [],
        masked=1 if inp.decision.lower() == "mask" else 0,
        created_at=datetime.now(KST),
    )

    async with AsyncSessionLocal() as s:
        s.add(evt)
        await s.commit()
        await s.refresh(evt)

    return {"ok": True, "id": evt.id}

@router.get("/logs", response_model=List[LogOut])
async def list_logs(
    host: Optional[str] = Query(None),
    decision: Optional[str] = Query(None, regex="^(allow|mask|block)$"),
    tag: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO-8601(KST)"),
    limit: int = Query(100, ge=1, le=1000),
):
    stmt = select(LogEvent).order_by(LogEvent.id.desc()).limit(limit)
    if host:
        stmt = stmt.filter(LogEvent.host == host.lower())
    if decision:
        stmt = stmt.filter(LogEvent.decision == decision.lower())
    if tag:
        stmt = stmt.filter(LogEvent.tags.like(f'%{tag}%'))
    if since:
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(since)
            stmt = stmt.filter(LogEvent.created_at >= ts)
        except Exception:
            raise HTTPException(status_code=400, detail="since 형식 오류(ISO-8601)")

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(stmt)).scalars().all()

    return [
        LogOut(
            id=r.id, time=r.time, interface=r.interface, method=r.method, scheme=r.scheme,
            host=r.host, port=r.port, path=r.path, query=r.query, client_ip=r.client_ip,
            tags=r.tags or [], decision=r.decision, reason=r.reason, rules_hit=r.rules_hit or [],
            body_sha256=r.body_sha256, body_preview=r.body_preview,
            body_masked_preview=r.body_masked_preview,
            created_at=r.created_at.astimezone(KST).isoformat(),
        )
        for r in rows
    ]

@router.get("/logs/{log_id}", response_model=LogOut)
async def get_log(log_id: int):
    async with AsyncSessionLocal() as s:
        row = await s.get(LogEvent, log_id)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return LogOut(
            id=row.id, time=row.time, interface=row.interface, method=row.method, scheme=row.scheme,
            host=row.host, port=row.port, path=row.path, query=row.query, client_ip=row.client_ip,
            tags=row.tags or [], decision=row.decision, reason=row.reason, rules_hit=row.rules_hit or [],
            body_sha256=row.body_sha256, body_preview=row.body_preview,
            body_masked_preview=row.body_masked_preview,
            created_at=row.created_at.astimezone(KST).isoformat(),
        )
