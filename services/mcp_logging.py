# services/mcp_logging.py
from __future__ import annotations

import uuid
from typing import Dict, Any, List
from urllib.parse import urlparse
import ipaddress

from sqlalchemy.orm import Session

from models import McpConfigEntry
from schemas import McpInItem, McpInResponse


class McpLoggingService:
    @staticmethod
    def _classify_server_type_and_scope(conf: Dict[str, Any]) -> tuple[str, str]:
        """
        개별 MCP 서버 설정(conf)에 대해
        - server_type: 'process' or 'http'
        - server_scope: 'local' or 'external'
        를 판별 (server_scope는 스냅샷 전체 mcp_scope 계산에만 사용, DB에는 직접 저장하지 않음)
        """
        # 1) 타입 판별
        if conf.get("type") == "http" or "url" in conf:
            server_type = "http"
        else:
            server_type = "process"

        # 2) scope 판별
        if server_type == "process":
            # 프로세스 실행형 MCP는 로컬에서 뜨는 것으로 간주
            return server_type, "local"

        # http MCP: URL 기준으로 local / external 판별
        url = conf.get("url", "") or ""
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
        except Exception:
            return server_type, "external"

        # localhost 계열
        if host in {"localhost", "127.0.0.1"}:
            return server_type, "local"

        # IP 주소인 경우
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback:
                return server_type, "local"
            return server_type, "external"
        except ValueError:
            # 도메인 문자열인 경우 → 외부로 간주
            return server_type, "external"

    @staticmethod
    def _calc_mcp_scope(status: str, server_scopes: List[str]) -> str:
        """
        스냅샷 전체 기준 mcp_scope 계산

        - status == 'delete' → 'deleted'
        - 그 외:
            * 하나라도 external 이면 'external'
            * 모두 local 이면 'local'
            * (서버가 없으면 기본 'local')
        """
        st = (status or "").lower()
        if st == "delete":
            return "deleted"

        if any(s == "external" for s in server_scopes):
            return "external"
        return "local"

    @staticmethod
    def handle(db: Session, item: McpInItem) -> McpInResponse:
        snapshot_id = uuid.uuid4().hex

        # 기본 메타 값 정리
        agent_time = item.time
        public_ip = item.public_ip or ""
        private_ip = item.private_ip
        host = item.host or "unknown"
        pc_name = item.pc_name or "unknown"
        status = (item.status or "").lower()
        file_path = item.file_path

        # 원본 config_raw 전체
        config_raw = item.config_raw or {}
        mcp_servers = {}
        if isinstance(config_raw, dict):
            mcp_servers = config_raw.get("mcpServers") or {}

        # 1) 서버별 타입/스코프 먼저 계산
        #    (name, conf, server_type, server_scope) 리스트
        servers_data: List[tuple[str, Dict[str, Any], str, str]] = []
        server_scopes: List[str] = []

        if isinstance(mcp_servers, dict):
            for name, conf in mcp_servers.items():
                if not isinstance(conf, dict):
                    continue
                server_type, server_scope = McpLoggingService._classify_server_type_and_scope(conf)
                servers_data.append((str(name), conf, server_type, server_scope))
                server_scopes.append(server_scope)

        # 2) 스냅샷 전체 mcp_scope 계산 (행마다 동일하게 들어감)
        mcp_scope = McpLoggingService._calc_mcp_scope(status, server_scopes)

        entries: List[McpConfigEntry] = []

        # 3) MCP 서버가 하나라도 있으면 서버별로 row 생성
        if servers_data:
            for name, conf, server_type, server_scope in servers_data:
                entry = McpConfigEntry(
                    # 스냅샷 공통 메타
                    snapshot_id     = snapshot_id,
                    agent_time      = agent_time,
                    public_ip       = public_ip,
                    private_ip      = private_ip,
                    host            = host,
                    pc_name         = pc_name,
                    status          = status,
                    file_path       = file_path,
                    mcp_scope       = mcp_scope,     # 스냅샷 기준 scope
                    config_raw_json = config_raw,

                    # MCP 서버 개별 정보
                    mcp_name     = name,
                    server_type  = server_type,      # 'process' / 'http'
                    # server_scope는 DB에 별도 컬럼 없음 (local/external 정보는 mcp_scope 계산에만 사용)
                    command      = conf.get("command"),
                    args_json    = conf.get("args"),
                    env_json     = conf.get("env"),
                    url          = conf.get("url"),
                    headers_json = conf.get("headers"),
                )
                entries.append(entry)
        else:
            # MCP 서버가 없는 스냅샷(예: status=delete 또는 아직 MCP 미사용)
            entry = McpConfigEntry(
                snapshot_id     = snapshot_id,
                agent_time      = agent_time,
                public_ip       = public_ip,
                private_ip      = private_ip,
                host            = host,
                pc_name         = pc_name,
                status          = status,
                file_path       = file_path,
                mcp_scope       = mcp_scope,
                config_raw_json = config_raw,

                mcp_name     = None,
                server_type  = None,
                command      = None,
                args_json    = None,
                env_json     = None,
                url          = None,
                headers_json = None,
            )
            entries.append(entry)

        # 4) DB 저장
        db.add_all(entries)
        db.flush()

        return McpInResponse(
            snapshot_id=snapshot_id,
            mcp_scope=mcp_scope,
            total_servers=len(servers_data),
        )
