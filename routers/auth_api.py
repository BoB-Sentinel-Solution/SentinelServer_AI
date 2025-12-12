# routers/auth_api.py
from __future__ import annotations

import os, base64, hashlib, hmac, secrets, logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import AdminAccountRecord

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])  # ✅ app.include_router(..., prefix="/api") 쓰는 스타일 유지


# ---- password hashing (PBKDF2) ----
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))

def hash_password(pw: str, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(dk)}"

def verify_password(stored: str, pw: str) -> bool:
    try:
        algo, it_s, salt_s, dk_s = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        it = int(it_s)
        salt = _b64d(salt_s)
        expected = _b64d(dk_s)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, it)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False

def new_api_key() -> str:
    return secrets.token_urlsafe(48)

def _admin_bypass_key() -> str:
    # ✅ 런타임에서 읽기 (환경변수 핫스왑 가능)
    return os.environ.get("ADMIN_KEY", "").strip()

def _get_or_create_admin(db: Session) -> AdminAccountRecord:
    rec = db.get(AdminAccountRecord, 1)
    if rec:
        return rec

    # 최초 부팅 시 계정 생성
    username = os.environ.get("ADMIN_ID", "").strip() or "admin"
    password = os.environ.get("ADMIN_PW", "").strip()

    if not password:
        # 운영 안전: 기본은 비번을 로그에 직접 출력하지 않음.
        # 정말 필요하면 AUTH_PRINT_INIT_PW=1 로만 출력되게.
        password = secrets.token_urlsafe(16)
        if os.environ.get("AUTH_PRINT_INIT_PW", "").strip() == "1":
            logger.warning("[AUTH] Initial admin password generated: %s", password)
        else:
            logger.warning("[AUTH] Initial admin password generated (hidden). Set ADMIN_PW or AUTH_PRINT_INIT_PW=1 for dev.")

    rec = AdminAccountRecord(
        id=1,
        username=username,
        password_hash=hash_password(password),
        api_key=new_api_key(),
        version=1,
        updated_at=datetime.now(),
    )
    db.add(rec)
    db.flush()   # ✅ get_db()가 commit하므로 여기선 flush만
    return rec

def require_admin(
    db: Session = Depends(get_db),
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> AdminAccountRecord:
    # (선택) 운영 긴급 우회키
    bypass = _admin_bypass_key()
    if bypass and x_admin_key == bypass:
        return _get_or_create_admin(db)

    rec = _get_or_create_admin(db)
    if not x_admin_key or x_admin_key != rec.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")
    return rec


# ---- Schemas ----
class LoginIn(BaseModel):
    username: str
    password: str

class LoginOut(BaseModel):
    api_key: str
    username: str

class ChangeIdIn(BaseModel):
    new_username: str = Field(min_length=1, max_length=64)

class ChangePwIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=256)

class ChangeOut(BaseModel):
    api_key: str
    username: str
    version: int
    updated_at: str


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    rec = _get_or_create_admin(db)
    if body.username != rec.username or not verify_password(rec.password_hash, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username/password")

    # 로그인 성공 시에도 키 회전하고 싶으면 아래 주석 해제
    # rec.api_key = new_api_key()
    # rec.version = int(rec.version or 1) + 1
    # rec.updated_at = datetime.now()
    # db.add(rec); db.flush()

    return LoginOut(api_key=rec.api_key, username=rec.username)

@router.get("/auth/me")
def me(rec: AdminAccountRecord = Depends(require_admin)):
    return {
        "username": rec.username,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
        "version": int(rec.version or 1),
    }

@router.put("/auth/id", response_model=ChangeOut)
def change_id(
    body: ChangeIdIn,
    db: Session = Depends(get_db),
    rec: AdminAccountRecord = Depends(require_admin),
) -> ChangeOut:
    u = body.new_username.strip()
    if not u:
        raise HTTPException(status_code=400, detail="new_username cannot be blank")

    rec.username = u
    rec.api_key = new_api_key()  # ✅ 변경 즉시 기존 세션 키 무효화
    rec.version = int(rec.version or 1) + 1
    rec.updated_at = datetime.now()
    db.add(rec)
    db.flush()

    return ChangeOut(
        api_key=rec.api_key,
        username=rec.username,
        version=int(rec.version or 1),
        updated_at=rec.updated_at.isoformat(),
    )

@router.put("/auth/password", response_model=ChangeOut)
def change_password(
    body: ChangePwIn,
    db: Session = Depends(get_db),
    rec: AdminAccountRecord = Depends(require_admin),
) -> ChangeOut:
    rec.password_hash = hash_password(body.new_password)
    rec.api_key = new_api_key()  # ✅ 변경 즉시 기존 세션 키 무효화
    rec.version = int(rec.version or 1) + 1
    rec.updated_at = datetime.now()
    db.add(rec)
    db.flush()

    return ChangeOut(
        api_key=rec.api_key,
        username=rec.username,
        version=int(rec.version or 1),
        updated_at=rec.updated_at.isoformat(),
    )
