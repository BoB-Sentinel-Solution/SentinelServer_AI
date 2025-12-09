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

    # Reason 페이지용 추가 정보
    reason = Column(Text, nullable=True)          # 한 줄 분석 결과
    reason_type = Column(String(32), nullable=True)   # "intentional" / "negligent" / "unknown"
    risk_category = Column(String(64), nullable=True) # 예: "신원 정보 유출"
    risk_pattern = Column(String(128), nullable=True) # 예: "NAME + PHONE + ADDRESS"

class McpConfigEntry(Base):
    """
    한 레코드 = MCP 설정 스냅샷(snapshot_id) 안의 MCP 서버 1개

    - 같은 snapshot_id 는 같은 MCP 설정 파일 상태(한 번 전송)를 의미
    - status:
        * 'activate' : 파일이 존재하고, 해당 시점의 MCP 설정 전체 스냅샷
        * 'delete'   : MCP 설정 파일 자체가 삭제된 이벤트
    - mcp_scope:
        * 'local'     : 이 MCP 서버가 로컬(MCP 프로세스 / 로컬/사설 HTTP)에서 동작
        * 'external'  : 이 MCP 서버가 외부 도메인/공인 IP HTTP MCP
        * 'deleted'   : 파일 삭제 스냅샷 등 MCP 자체가 없는 이벤트 행에 사용 가능
    """
    __tablename__ = "mcp_config_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 스냅샷 공통 메타 정보
    snapshot_id  = Column(String(64), index=True, nullable=False)  # 같은 전송 묶음 ID
    agent_time   = Column(String(32), nullable=False)              # 에이전트 JSON "time"
    public_ip    = Column(String(45), nullable=False)
    private_ip   = Column(String(45))
    host         = Column(String(64), nullable=False)              # 예: 'claude'
    pc_name      = Column(String(255), nullable=False)             # 예: 'enha0527'
    status       = Column(String(32), nullable=False)              # 'activate' / 'delete'
    file_path    = Column(Text, nullable=False)                    # MCP 설정 파일 경로

    # MCP 설정 원본 전체 (config_raw 그대로)
    config_raw_json = Column(JSON, nullable=False)

    # MCP 서버 개별 정보
    mcp_name    = Column(String(128))                              # 'github', 'ida-pro-mcp', ...
    mcp_scope   = Column(String(32))                               # 'local' / 'external' / 'deleted'
    server_type = Column(String(32))                               # 'process' / 'http'

    command     = Column(Text)                                     # process형 command
    args_json   = Column(JSON)                                     # args 배열
    env_json    = Column(JSON)                                     # env 딕셔너리
    url         = Column(Text)                                     # http형 URL
    headers_json = Column(JSON)                                    # http형 headers

    # 메타
    created_at  = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
