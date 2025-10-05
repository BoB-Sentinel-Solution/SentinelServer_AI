# repositories/log_repo.py
from sqlalchemy.orm import Session
from models import LogRecord

class LogRepository:
    @staticmethod
    def create(db: Session, rec: LogRecord) -> LogRecord:
        db.add(rec)
        db.flush()
        return rec

    @staticmethod
    def get(db: Session, request_id: str) -> LogRecord | None:
        return db.get(LogRecord, request_id)
