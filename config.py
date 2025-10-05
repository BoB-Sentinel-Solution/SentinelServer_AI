# config.py
from pydantic import BaseSettings
from pathlib import Path

# 프로젝트 루트 기준 ./db/sentinel.db 에 저장
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "db"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # 폴더 자동 생성

class Settings(BaseSettings):
    # SQLite 절대경로 권장
    DATABASE_URL: str = f"sqlite:///{(DATA_DIR / 'sentinel.db').as_posix()}"

    class Config:
        env_file = ".env"

settings = Settings()
