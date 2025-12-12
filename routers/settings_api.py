# routers/settings_api.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import SettingsRecord
from db import SessionLocal  # ✅ get_db가 없으니 SessionLocal을 가져와서 여기서 정의
from routers.auth_api import require_admin  # ✅ X-Admin-Key 검증(= DB api_key + (선택) ADMIN_KEY 우회)

router = APIRouter(prefix="/api", tags=["settings"])


# ✅ 2번 방식: 라우터 내부에서 get_db 직접 정의
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _dump_model(m) -> dict:
    if m is None:
        return {}
    if hasattr(m, "model_dump"):
        return m.model_dump()
    if hasattr(m, "dict"):
        return m.dict()
    return dict(m)


# =========================
# ✅ schemas.py 의존 제거 (ImportError 방지)
# =========================
class SettingsConfig(BaseModel):
    # 서버 정책(모든 요청에 영향)
    response_method: str = Field(default="mask")  # "mask" | "allow" | "block"

    # 서버에 저장되는 서비스 필터
    # settings.js 와 동일한 구조:
    # service_filters: {
    #   llm: { gpt, gemini, claude, deepseek, groq },
    #   mcp: { gpt_desktop, claude_desktop, vscode_copilot }
    # }
    service_filters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "llm": {
                "gpt": True,
                "gemini": True,
                "claude": True,
                "deepseek": True,
                "groq": True,
            },
            "mcp": {
                "gpt_desktop": True,
                "claude_desktop": True,
                "vscode_copilot": True,
            },
        }
    )


class SettingsOut(BaseModel):
    config: SettingsConfig
    version: int
    updated_at: Optional[str] = None


class SettingsUpdateIn(BaseModel):
    config: SettingsConfig
    version: int


def _default_config() -> SettingsConfig:
    return SettingsConfig()


def _get_or_create_settings(db: Session) -> SettingsRecord:
    rec = db.get(SettingsRecord, 1)
    if rec:
        return rec

    # ✅ 생성 시 레이스 방어 (동시에 여러 요청이 들어오면 IntegrityError 가능)
    rec = SettingsRecord(id=1)
    rec.set_config(_dump_model(_default_config()))
    rec.version = 1
    rec.updated_at = datetime.now()
    db.add(rec)

    try:
        db.commit()       # ✅ 최초 생성은 여기서 커밋/반영
        db.refresh(rec)
        return rec
    except IntegrityError:
        db.rollback()
        rec2 = db.get(SettingsRecord, 1)
        if rec2:
            return rec2
        raise


@router.get("/settings", response_model=SettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),  # ✅ X-Admin-Key 검증은 auth_api 로 통일
) -> SettingsOut:
    rec = _get_or_create_settings(db)

    cfg_dict = rec.get_config() or {}
    try:
        cfg = SettingsConfig(**cfg_dict)
    except Exception:
        cfg = _default_config()

    return SettingsOut(
        config=cfg,
        version=int(rec.version or 1),
        updated_at=rec.updated_at.isoformat() if rec.updated_at else None,
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    body: SettingsUpdateIn,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),  # ✅ X-Admin-Key 검증은 auth_api 로 통일
) -> SettingsOut:
    rec = _get_or_create_settings(db)

    # ✅ 낙관적 락(버전 충돌 감지)
    if body.version is not None and int(body.version) != int(rec.version or 1):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Settings version mismatch (server={rec.version}, client={body.version})"
        )

    new_cfg = _dump_model(body.config)
    rec.set_config(new_cfg)
    rec.version = int(rec.version or 1) + 1
    rec.updated_at = datetime.now()
    db.add(rec)

    db.commit()
    db.refresh(rec)

    return SettingsOut(
        config=SettingsConfig(**(rec.get_config() or {})),
        version=int(rec.version or 1),
        updated_at=rec.updated_at.isoformat() if rec.updated_at else None,
    )
