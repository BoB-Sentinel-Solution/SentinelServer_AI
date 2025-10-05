# routers/logs.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db import SessionLocal, Base, engine
from schemas import InItem, ServerOut
from services.db_logging import DbLoggingService

router = APIRouter()

# 간단 자동 생성 (운영은 Alembic 권장)
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.get("/healthz")
def healthz():
    return {"ok": True}

@router.post("/logs", response_model=ServerOut)
def logs(item: InItem, db: Session = Depends(get_db)) -> ServerOut:
    return DbLoggingService.handle(db, item)
