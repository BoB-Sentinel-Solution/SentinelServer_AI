# config.py  — pydantic v2 호환 + ./db/sentinel.db 기본 경로 + .env 우선
from __future__ import annotations

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 프로젝트 루트(이 파일이 sentinel_server/ 안에 있다고 가정)
BASE_DIR: Path = Path(__file__).resolve().parent

# ./db 디렉터리 보장
DATA_DIR: Path = BASE_DIR / "db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 기본 SQLite 파일 경로
DEFAULT_DB_PATH: Path = DATA_DIR / "sentinel.db"
DEFAULT_SQLITE_URL: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


class Settings(BaseSettings):
    """
    - 기본값: sqlite:///./db/sentinel.db
    - .env의 DATABASE_URL이:
        * 완전한 DSN (예: postgresql://..., sqlite:///...) 이면 그대로 사용
        * 경로(상대/절대)만 주면 자동으로 sqlite:/// 경로로 변환
    """
    ENV: str = Field(default="production")
    DEBUG: bool = Field(default=False)

    DATABASE_URL: str = Field(default=DEFAULT_SQLITE_URL, description="SQLAlchemy Database URL")

    # pydantic v2 설정: .env 사용, 여분 필드 무시
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """
        .env에서 DATABASE_URL을 파일 경로로만 줬을 때 자동으로 sqlite:/// 접두사를 붙이고,
        상대경로는 BASE_DIR 기준으로 정규화한다.
        이미 '://` 스킴이 있으면 그대로 둔다.
        """
        if "://" in v:
            return v  # 이미 DSN 형태

        # 파일 경로로 간주
        p = Path(v)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()

        # 상위 디렉터리 생성 보장
        p.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{p.as_posix()}"


settings = Settings()
