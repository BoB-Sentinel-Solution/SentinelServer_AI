# routers/mcp.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import SessionLocal, Base, engine
from schemas import McpInItem, McpInResponse
from services.mcp_logging import McpLoggingService

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


@router.post("/mcp", response_model=McpInResponse)
def mcp_config(item: McpInItem, db: Session = Depends(get_db)) -> McpInResponse:
    """
    MCP 설정 파일 업로드 엔드포인트
    - 에이전트에서 claude_desktop_config.json 등 내용을 전송
    - 서버에서 스냅샷 + MCP 서버별 row 로 분해하여 저장
    """
    return McpLoggingService.handle(db, item)
