# routers/dashboard_api.py
from __future__ import annotations

import json
import re
import ipaddress
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import cast, Text, func  # JSON 검색 + interface 필터용

from db import SessionLocal, Base, engine
from models import LogRecord, McpConfigEntry
from config import settings

router = APIRouter()  # 접두는 app.py에서 prefix="/api"로 부여

# https://123.45.67.89/ 이런 형태의 URL 탐지용 정규표현식
IP_URL_RE = re.compile(
    r"^https?://(?:(?:\d{1,3}\.){3}\d{1,3})(?::\d+)?(?:/|$)",
    re.IGNORECASE,
)

# 운영에서는 Alembic 권장. 개발 편의를 위해 안전 생성.
Base.metadata.create_all(bind=engine)

# --- DB 세션 DI ---
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


# --- 선택적 API 키 인증 ---
def require_admin(x_admin_key: str | None = Header(default=None)):
    """
    - .env 의 DASHBOARD_API_KEY 가 설정되어 있다면 X-Admin-Key 헤더로 검증
    - 없으면 무인증 허용
    """
    if settings.DASHBOARD_API_KEY:
        if x_admin_key != settings.DASHBOARD_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )


# ---------- 요약 API ----------
@router.get("/summary", dependencies=[Depends(require_admin)])
def dashboard_summary(
    interface: str | None = None,  # ?interface=LLM / MCP 등 필터
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    대시보드 요약 데이터:
    - total_sensitive: has_sensitive=True 총 건수
    - total_blocked: 차단된 요청 수 (allow=False 또는 action startswith("block"))
    - type_ratio: 라벨 비율(엔티티 라벨 카운트, 전체 기간)
    - type_detected: 유형별 탐지 횟수(전체 기간)
    - type_blocked: 유형별 차단 횟수(파일 유사 차단은 FILE_SIMILAR)
    - hourly_attempts: 0~23시 카운트(모든 요청, 전체 기간)
    - hourly_type: 시간대별(0~23) · 라벨별 탐지 건수 (has_sensitive=True)
    - recent_logs: 최근 20건 (민감값 미노출)
    - ip_band_detected / ip_band_blocked: 공인IP /16 대역별 탐지/차단 건수

    - today_sensitive / today_blocked: 오늘 탐지·차단 건수
    - today_hourly: 오늘 시간대별 탐지 건수 [0..23]
    - today_type_ratio: 오늘 탐지된 라벨 비율

    서비스 기반 리포트용:
    - service_usage_by_host: 호스트별 전체 호출 수
    - service_sensitive_by_host: 호스트별 민감정보 탐지 수
    - service_blocked_by_host: 호스트별 차단 수

    파일 기반 리포트용:
    - file_detect_by_ext: 확장자별(attachment.format) 민감정보 탐지 건수
    - file_label_by_ext: 확장자+라벨별 탐지 건수
    - recent_file_logs: 최근 파일 첨부 요청(최대 20건)

    interface 파라미터가 주어지면 해당 interface 로그만 집계 (예: LLM, MCP)
    """

    # --- 쿼리 구성: interface 있으면 필터 ---
    query = db.query(LogRecord)
    if interface:
        q_interface = interface.strip().lower()
        query = query.filter(func.lower(LogRecord.interface) == q_interface)

    rows: List[LogRecord] = query.order_by(LogRecord.created_at.desc()).all()

    # 오늘 날짜 (created_at 이 timezone-aware 라면 적절히 맞춰야 함)
    today: date = datetime.utcnow().date()

    total_sensitive = 0
    total_blocked = 0

    type_ratio: Dict[str, int] = defaultdict(int)
    type_detected: Dict[str, int] = defaultdict(int)

    # 새로 추가된 "탐지" 집계
    ip_band_detected: Dict[str, int] = defaultdict(int)

    # 기존 "차단" 집계(호환 유지)
    type_blocked: Dict[str, int] = defaultdict(int)
    ip_band_blocked: Dict[str, int] = defaultdict(int)

    # 서비스(호스트)별 집계
    service_usage_by_host: Dict[str, int] = defaultdict(int)
    service_sensitive_by_host: Dict[str, int] = defaultdict(int)
    service_blocked_by_host: Dict[str, int] = defaultdict(int)

    # 파일 기반 집계
    file_detect_by_ext: Dict[str, int] = defaultdict(int)
    file_label_by_ext: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    recent_file_logs: List[Dict[str, Any]] = []

    # 오늘 기준 통계
    today_sensitive = 0
    today_blocked = 0
    today_type_ratio: Dict[str, int] = defaultdict(int)

    # 시간대별 통계
    hourly_attempts = [0] * 24                 # 전체 요청 수
    today_hourly = [0] * 24                    # 오늘 탐지 건수
    hourly_type: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    recent_logs: List[Dict[str, Any]] = []

    for r in rows:
        created = r.created_at
        created_date: date | None = created.date() if created else None
        hour: int | None = created.hour if created else None

        # ---- 서비스(호스트)별 공통 집계 ----
        host_key = r.host or "unknown"
        service_usage_by_host[host_key] += 1

        # ---- 파일 관련 정보 파싱 (attachment.format) ----
        file_ext: str | None = None
        att = r.attachment
        if att:
            if isinstance(att, dict):
                file_ext = (att.get("format") or "").strip().lower() or None
            elif isinstance(att, str):
                try:
                    att_json = json.loads(att)
                    file_ext = (att_json.get("format") or "").strip().lower() or None
                except Exception:
                    file_ext = None

        # ---- 공통: 시간대별 "시도" 카운트 (모든 요청) ----
        if hour is not None and 0 <= hour < 24:
            try:
                hourly_attempts[hour] += 1
            except Exception:
                pass

        # ---- 차단 여부 미리 계산 ----
        action = (r.action or "")
        is_blocked = (r.allow is False) or action.startswith("block")

        # === 탐지 관련 집계 ===
        if r.has_sensitive:
            total_sensitive += 1
            service_sensitive_by_host[host_key] += 1

            # 유형 비율/탐지 횟수: 엔티티 라벨 기준
            for e in (r.entities or []):
                label = e.get("label", "OTHER")
                type_ratio[label] += 1
                type_detected[label] += 1

                # 시간대별 유형 카운트
                if hour is not None and 0 <= hour < 24:
                    hourly_type[hour][label] += 1

                # 오늘 기준 유형 비율
                if created_date == today:
                    today_type_ratio[label] += 1

                # 파일 기반: 확장자+라벨별 카운트
                if file_ext:
                    file_label_by_ext[file_ext][label] += 1

            # /16 대역 탐지 건수
            if r.public_ip and r.public_ip.count(".") == 3:
                a, b, *_ = r.public_ip.split(".")
                ip_band_detected[f"{a}.{b}.*"] += 1

            # 오늘 탐지 건수 / 시간대별
            if created_date == today and hour is not None and 0 <= hour < 24:
                today_sensitive += 1
                try:
                    today_hourly[hour] += 1
                except Exception:
                    pass

            # 파일 기반: 확장자별 탐지 건수
            if file_ext:
                file_detect_by_ext[file_ext] += 1

        # === 차단 관련 집계(기존 로직 유지) ===
        if is_blocked:
            total_blocked += 1
            service_blocked_by_host[host_key] += 1

            if created_date == today:
                today_blocked += 1

            if r.entities:
                for e in r.entities:
                    type_blocked[e.get("label", "OTHER")] += 1
            # 파일 유사 차단인데 엔티티가 없을 때는 FILE_SIMILAR로 표기
            if r.file_blocked and not r.entities:
                type_blocked["FILE_SIMILAR"] += 1

            if r.public_ip and r.public_ip.count(".") == 3:
                a, b, *_ = r.public_ip.split(".")
                ip_band_blocked[f"{a}.{b}.*"] += 1

        # === 최근 로그 20건 (민감값 미노출) ===
        if len(recent_logs) < 20:
            recent_logs.append({
                "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                "host": r.host,
                "hostname": r.hostname,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "internal_ip": r.private_ip,  # 대시보드 테이블에서 쓰는 필드
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "entities": [{"label": (e.get("label") or "")} for e in (r.entities or [])],
                "prompt": (r.prompt[:120] + "…") if r.prompt and len(r.prompt) > 120 else (r.prompt or ""),
            })

        # === 최근 파일 로그 20건 (첨부 있는 경우만) ===
        if file_ext and len(recent_file_logs) < 20:
            recent_file_logs.append({
                "time": r.created_at.isoformat() if r.created_at else getattr(r, "time", None),
                "host": r.host,
                "hostname": r.hostname,
                "public_ip": r.public_ip,
                "private_ip": r.private_ip,
                "internal_ip": r.private_ip,  # 대시보드 테이블에서 쓰는 필드
                "action": r.action,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "blocked": is_blocked,
                "file_ext": file_ext,
            })

    # hourly_type 은 {시간(int): {라벨:카운트}} → JSON 직렬화 위해 키를 문자열로
    hourly_type_serialized: Dict[str, Dict[str, int]] = {
        str(h): dict(type_counts) for h, type_counts in hourly_type.items()
    }

    # file_label_by_ext 도 dict 로 변환
    file_label_by_ext_serialized: Dict[str, Dict[str, int]] = {
        ext: dict(label_counts) for ext, label_counts in file_label_by_ext.items()
    }

    return {
        # 전체 기간 통계
        "total_sensitive": total_sensitive,
        "total_blocked": total_blocked,
        "type_ratio": dict(type_ratio),
        "type_detected": dict(type_detected),
        "type_blocked": dict(type_blocked),
        "hourly_attempts": hourly_attempts,
        "hourly_type": hourly_type_serialized,
        "recent_logs": recent_logs,
        "ip_band_detected": dict(ip_band_detected),
        "ip_band_blocked": dict(ip_band_blocked),

        # 서비스(호스트)별 통계
        "service_usage_by_host": dict(service_usage_by_host),
        "service_sensitive_by_host": dict(service_sensitive_by_host),
        "service_blocked_by_host": dict(service_blocked_by_host),

        # 파일 기반 통계
        "file_detect_by_ext": dict(file_detect_by_ext),
        "file_label_by_ext": file_label_by_ext_serialized,
        "recent_file_logs": recent_file_logs,

        # 오늘 기준 통계
        "today_sensitive": today_sensitive,
        "today_blocked": today_blocked,
        "today_hourly": today_hourly,
        "today_type_ratio": dict(today_type_ratio),
    }


# ---------- 전체 로그 조회 API (Logs 페이지용) ----------
@router.get("/logs", dependencies=[Depends(require_admin)])
def list_logs(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Logs 페이지용 전체 로그 조회 API

    쿼리 파라미터:
    - page: 페이지 번호(1부터)
    - page_size: 페이지 크기 (최대 100)
    - q: 검색 키워드
    - category: 검색 대상 컬럼
      - prompt | host | pc_name | public_ip | private_ip | entity
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

    query = db.query(LogRecord)

    # 검색 필터
    if q:
        like = f"%{q}%"
        cat = (category or "").lower()

        if cat == "prompt":
            query = query.filter(LogRecord.prompt.ilike(like))
        elif cat == "host":
            query = query.filter(LogRecord.host.ilike(like))
        elif cat == "pc_name":
            query = query.filter(LogRecord.hostname.ilike(like))
        elif cat == "public_ip":
            query = query.filter(LogRecord.public_ip.ilike(like))
        elif cat == "private_ip":
            query = query.filter(LogRecord.private_ip.ilike(like))
        elif cat == "entity":
            # entities(JSON) 문자열 검색
            query = query.filter(cast(LogRecord.entities, Text).ilike(like))
        else:
            # 카테고리 없으면 여러 컬럼 OR 검색
            query = query.filter(
                (LogRecord.prompt.ilike(like))
                | (LogRecord.host.ilike(like))
                | (LogRecord.hostname.ilike(like))
                | (LogRecord.public_ip.ilike(like))
                | (LogRecord.private_ip.ilike(like))
            )

    query = query.order_by(LogRecord.created_at.desc())

    total = query.count()
    rows: List[LogRecord] = (
        query.offset((page - 1) * page_size).limit(page_size).all()
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append({
            "id": getattr(r, "request_id", None),
            "prompt": r.prompt,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "time": r.created_at.isoformat() if r.created_at else None,
            "host": r.host,
            "hostname": r.hostname,
            "public_ip": r.public_ip,
            "internal_ip": r.private_ip,            # 프론트에서는 Internal IP/Private IP 컬럼으로 사용
            "interface": r.interface,
            "action": r.action,
            "allow": r.allow,
            "has_sensitive": r.has_sensitive,
            "file_blocked": r.file_blocked,
            "entities": r.entities or [],
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/mcp/config_summary")
def mcp_config_summary(db: Session = Depends(get_db)):
    """
    MCP 설정 파일 기반 CONFIG 리포트 요약

    - active_total: 현재 활성화된 MCP 서버 개수
    - active_rank: MCP 이름별 활성 개수 순위
    - type_distribution: local / external / other 비율
    - timeline: 최근 스냅샷 기준 등록/변경/삭제 타임라인
    - prediction: 정규표현식을 이용한 URL 기반 악성 징후 진단 결과
    """

    # ---- 1) 현재 활성 스냅샷 (pc_name+host+file_path 별 최신) ----
    latest_sub = (
        db.query(
            McpConfigEntry.pc_name.label("pc_name"),
            McpConfigEntry.host.label("host"),
            McpConfigEntry.file_path.label("file_path"),
            func.max(McpConfigEntry.agent_time).label("max_time"),
        )
        .group_by(
            McpConfigEntry.pc_name,
            McpConfigEntry.host,
            McpConfigEntry.file_path,
        )
        .subquery()
    )

    current_entries: List[McpConfigEntry] = (
        db.query(McpConfigEntry)
        .join(
            latest_sub,
            (McpConfigEntry.pc_name == latest_sub.c.pc_name)
            & (McpConfigEntry.host == latest_sub.c.host)
            & (McpConfigEntry.file_path == latest_sub.c.file_path)
            & (McpConfigEntry.agent_time == latest_sub.c.max_time),
        )
        .filter(func.lower(McpConfigEntry.status) != "delete")
        .all()
    )

    # ---- 2) 활성 MCP 개수 / 순위 / 타입 분포 ----
    active_total = sum(1 for e in current_entries if e.mcp_name)

    rank_counts: Dict[str, int] = {}
    type_dist = {"local": 0, "external": 0, "other": 0}

    for e in current_entries:
        name = (e.mcp_name or "UNKNOWN").strip() or "UNKNOWN"
        rank_counts[name] = rank_counts.get(name, 0) + 1

        scope = (e.mcp_scope or "").lower()
        if scope == "local":
            type_dist["local"] += 1
        elif scope == "external":
            type_dist["external"] += 1
        else:
            type_dist["other"] += 1

    active_rank = [
        {"mcp_name": name, "count": count}
        for name, count in sorted(
            rank_counts.items(), key=lambda kv: kv[1], reverse=True
        )
    ]

    # ---- 3) 최근 스냅샷 기반 타임라인 ----
    # snapshot_id 별 최신 시간만 뽑아서 50개 제한
    snap_rows = (
        db.query(
            McpConfigEntry.snapshot_id,
            func.max(McpConfigEntry.agent_time).label("agent_time"),
        )
        .group_by(McpConfigEntry.snapshot_id)
        .order_by(func.max(McpConfigEntry.agent_time).desc())
        .limit(50)
        .all()
    )

    snap_ids = [r.snapshot_id for r in snap_rows]
    timeline: List[Dict[str, Any]] = []

    if snap_ids:
        all_snap_entries: List[McpConfigEntry] = (
            db.query(McpConfigEntry)
            .filter(McpConfigEntry.snapshot_id.in_(snap_ids))
            .all()
        )

        # snapshot_id -> 메타 + 엔트리 목록
        snaps: Dict[str, Dict[str, Any]] = {}
        for e in all_snap_entries:
            s = snaps.setdefault(
                e.snapshot_id,
                {
                    "agent_time": e.agent_time,
                    "pc_name": e.pc_name,
                    "private_ip": e.private_ip,
                    "host": e.host,
                    "file_path": e.file_path,
                    "status": e.status,
                    "entries": [],
                },
            )
            s["entries"].append(e)

        # 등록/변경/삭제 판별용: pc_name+host+file_path 기준으로 과거 존재 여부 체크
        sorted_by_time = sorted(
            snaps.values(), key=lambda x: (x["agent_time"] or "")
        )
        seen_keys = set()
        for snap in sorted_by_time:
            key = (snap["pc_name"], snap["host"], snap["file_path"])
            st = (snap["status"] or "").lower()
            if st == "delete":
                event = "삭제"
            else:
                event = "등록" if key not in seen_keys else "변경"
            snap["event"] = event
            seen_keys.add(key)

        # 최신 순으로 10개만 타임라인에 노출
        latest_snaps = sorted(
            snaps.values(),
            key=lambda x: (x["agent_time"] or ""),
            reverse=True,
        )[:10]

        for snap in latest_snaps:
            entries = snap["entries"]
            names = sorted(
                {e.mcp_name for e in entries if e.mcp_name}
            )
            if not names:
                mcp_label = "-"
            elif len(names) == 1:
                mcp_label = names[0]
            else:
                mcp_label = f"{names[0]} 외 {len(names) - 1}개"

            scopes = { (e.mcp_scope or "").lower() for e in entries if e.mcp_scope }
            if "external" in scopes:
                type_label = "Remote"
            elif "local" in scopes:
                type_label = "Local"
            else:
                type_label = "기타"

            timeline.append(
                {
                    "time": snap["agent_time"],
                    "event": snap.get("event", ""),
                    "pc_name": snap["pc_name"],
                    "private_ip": snap["private_ip"],
                    "host": snap["host"],
                    "mcp": mcp_label,
                    "type": type_label,
                }
            )

    # ---- 4) 정규표현식 기반 악성 징후(PREDICTION) ----
    suspicious_entries: List[McpConfigEntry] = []
    for e in current_entries:
        url = (e.url or "").strip()
        if not url:
            continue
        if IP_URL_RE.search(url):
            suspicious_entries.append(e)

    if suspicious_entries:
        sus_mcp_names = sorted(
            { (e.mcp_name or "UNKNOWN") for e in suspicious_entries }
        )
        prediction = {
            "has_suspicious": True,
            "headline": "일부 MCP 서버 URL에서 직접 IP 기반 접속이 감지되었습니다.",
            "detail": (
                "현재 활성 MCP 중 "
                f"{len(sus_mcp_names)}개({', '.join(sus_mcp_names[:3])}"
                f"{' 등' if len(sus_mcp_names) > 3 else ''})의 URL이 "
                "https://IP 형태로 설정되어 있습니다. "
                "내부 테스트용이 아니라면, 도메인 기반 접속 및 서버 신뢰도 검토가 필요합니다."
            ),
        }
    else:
        prediction = {
            "has_suspicious": False,
            "headline": "현재 MCP 설정에서 명백한 악성 징후는 발견되지 않았습니다.",
            "detail": (
                "활성화된 MCP 서버들의 URL에서 직접 IP 기반 https 접속은 "
                "정규표현식 검사 기준으로 확인되지 않았습니다. "
                "현 시점에서는 기본 형식 상의 위험 요소는 낮은 편입니다."
            ),
        }

    return {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "active_total": active_total,
        "active_rank": active_rank,
        "type_distribution": type_dist,
        "timeline": timeline,
        "prediction": prediction,
    }

@router.get("/network/summary", dependencies=[Depends(require_admin)])
def network_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    네트워크 리포트(외부 IP / 사설망 / 의심 PC)용 요약 데이터.

    - public_band_usage: 공인 IP /16 대역별 사용 건수
    - public_band_count: 공인 IP 대역 개수 (PUBLIC 대역 개수 카드)
    - top_private_bands: 공인 IP 대역 기준 상위 3개 사설망 정보
    - suspicious_pcs: 외부 IP 사용 의심 PC 요약 (직접 노출 / 신규 출구)
    - suspicious_logs: 의심 PC 관련 로그 테이블용 레코드
    """

    # 모든 로그 (추후 기간 필터링이 필요하면 여기서 where 조건 추가)
    rows: List[LogRecord] = (
        db.query(LogRecord)
        .order_by(LogRecord.created_at.asc())
        .all()
    )

    # 1) 공인 IP 대역 사용 현황 (PUBLIC 대역)
    # key: "A.B.*"  (/16 대역)
    public_band_usage: Dict[str, int] = defaultdict(int)

    # 2) 공인 IP 대역별 연결 사설망 정보
    band_private_bands: Dict[str, set] = defaultdict(set)   # 사설망 /16 대역 집합
    band_pc_names: Dict[str, set] = defaultdict(set)        # 해당 대역 사용하는 PCName 집합
    band_sensitive_count: Dict[str, int] = defaultdict(int) # 중요정보 탐지 건수

    # 3) 외부 IP 사용 의심 PC 정보
    # key = (public_ip, private_ip, pc_name)
    suspicious_map: Dict[tuple, Dict[str, Any]] = {}

    # 4) 의심 로그 목록 (테이블용)
    suspicious_logs: List[Dict[str, Any]] = []

    for r in rows:
        pub = (r.public_ip or "").strip()
        priv = (r.private_ip or "").strip()
        pc_name = (r.hostname or "").strip() or "UNKNOWN"
        created = r.created_at
        created_str = created.isoformat() if created else (r.time or "")

        # ---------- 공인 IP 대역 집계 (PUBLIC 대역 개수 / 대역폭 사용 현황) ----------
        if pub:
            try:
                ip_obj = ipaddress.ip_address(pub)
                # 공인 IP만 대상 (사설/루프백 등은 제외)
                if ip_obj.is_global:
                    octets = pub.split(".")
                    if len(octets) == 4:
                        band = f"{octets[0]}.{octets[1]}.*"
                        public_band_usage[band] += 1

                        # 이 PUBLIC 대역을 사용하는 사설망 대역 목록 (PRIVATE IP 기준)
                        if priv:
                            try:
                                priv_obj = ipaddress.ip_address(priv)
                                if priv_obj.is_private:
                                    po = priv.split(".")
                                    if len(po) == 4:
                                        priv_band = f"{po[0]}.{po[1]}.*"
                                        band_private_bands[band].add(priv_band)
                            except ValueError:
                                pass

                        band_pc_names[band].add(pc_name)
                        if r.has_sensitive:
                            band_sensitive_count[band] += 1
            except ValueError:
                # 잘못된 IP 문자열은 무시
                pass

        # ---------- 외부 IP 사용 의심 PC 판별 ----------
        reason = None

        # (1) PUBLIC IP == PRIVATE IP  → 직접 인터넷 노출
        if pub and priv and pub == priv:
            reason = "direct_exposure"

        # (2) PRIVATE IP가 사설대역이 아님 → 신규 출구
        elif priv:
            try:
                priv_obj = ipaddress.ip_address(priv)
                if not priv_obj.is_private:
                    reason = "new_egress"
            except ValueError:
                # IP 형식이 아니면 무시
                pass

        if reason:
            key = (pub, priv, pc_name)
            prev = suspicious_map.get(key)
            # 같은 조합이면 더 최근 시간으로 갱신
            if not prev or prev["last_time"] < created_str:
                suspicious_map[key] = {
                    "public_ip": pub,
                    "private_ip": priv,
                    "pc_name": pc_name,
                    "reason": reason,        # "direct_exposure" or "new_egress"
                    "last_time": created_str,
                }

            # 이 로그도 "외부 IP 사용 의심 PC 로그" 테이블에 포함
            suspicious_logs.append({
                "time": created_str,
                "host": r.host,
                "pc_name": pc_name,
                "public_ip": pub,
                "private_ip": priv,
                "interface": r.interface,
                "action": r.action,
                "allow": r.allow,
                "has_sensitive": r.has_sensitive,
                "file_blocked": r.file_blocked,
                "entities": r.entities or [],
                "prompt": (
                    (r.prompt[:120] + "…")
                    if r.prompt and len(r.prompt) > 120
                    else (r.prompt or "")
                ),
            })

    # ---------- 대역폭 별 연결 사설망 (상위 3개) ----------
    band_items: List[Dict[str, Any]] = []
    for band, cnt in public_band_usage.items():
        priv_bands = sorted(band_private_bands.get(band, []))
        band_items.append({
            "public_band": band,                         # 예: "221.111.*"
            "total_logs": cnt,                           # 이 PUBLIC 대역으로 나간 전체 로그 수
            "private_band_count": len(priv_bands),       # 연결된 사설망 /16 대역 수
            "private_bands": priv_bands,                 # ["192.168.*", "172.16.*", ...]
            "pc_count": len(band_pc_names.get(band, [])),
            "sensitive_count": band_sensitive_count.get(band, 0),
        })

    # 사용량 기준 내림차순 정렬 후 상위 3개만 카드용으로 사용
    top_private_bands = sorted(
        band_items, key=lambda x: x["total_logs"], reverse=True
    )[:3]

    # ---------- 외부 IP 사용 의심 PC 정보 (카드용) ----------
    suspicious_pcs = sorted(
        suspicious_map.values(),
        key=lambda x: x["last_time"],
        reverse=True,
    )[:20]  # 카드에는 최대 20개만

    # 로그 테이블도 최신순 50개로 제한
    suspicious_logs = sorted(
        suspicious_logs,
        key=lambda x: x["time"],
        reverse=True,
    )[:50]

    return {
        # PUBLIC 대역 개수 카드 + PUBLIC 대역 파이 차트
        "public_band_usage": dict(public_band_usage),   # { "221.111.*": 10, ... }
        "public_band_count": len(public_band_usage),    # 예: 12

        # 대역폭 별 연결 사설망 (상위 3개 카드)
        "top_private_bands": top_private_bands,

        # 외부 IP 사용 의심 PC 정보 카드
        #  - 각 원소: {public_ip, private_ip, pc_name, reason("direct_exposure"/"new_egress"), last_time}
        "suspicious_pcs": suspicious_pcs,

        # 외부 IP 사용 의심 PC 로그 테이블
        "suspicious_logs": suspicious_logs,
    }

@router.get("/report/llm/file-summary")
def report_llm_file_summary(
    admin_key: str | None = Header(None, alias=settings.admin_header),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    LLM 인터페이스 중 파일(attachment) 이 있는 로그만 대상으로
    - 확장자별 개수 (도넛 차트용)
    - 확장자 x 라벨별 개수 (스택 바용)
    - 최근 20건 테이블
    을 반환
    """
    _require_admin(admin_key)

    # 1) 파일 첨부된 LLM 로그만 조회
    q = (
        db.query(LogRecord)
        .filter(
            LogRecord.interface == "llm",
            LogRecord.attachment.isnot(None),  # SQLite: IS NOT NULL
        )
        .order_by(LogRecord.created_at.desc())
    )

    rows: List[LogRecord] = q.limit(200).all()

    # 2) 도넛: 확장자별 개수
    donut_counts: Dict[str, int] = defaultdict(int)

    # 3) 스택 바: 확장자 x 라벨
    stacked_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # 4) 테이블: 최근 20건
    recent: List[Dict[str, Any]] = []

    for r in rows:
        att = r.attachment or {}
        ext = (att.get("format") or "unknown").lower()
        donut_counts[ext] += 1

        # 엔티티 라벨 집계
        for e in (r.entities or []):
            lab = (e.get("label") or "OTHER").upper()
            stacked_counts[ext][lab] += 1

        if len(recent) < 20:
            recent.append(
                {
                    "time": r.time,
                    "host": r.host,
                    "pc_name": r.hostname,   # PC 이름을 hostname 필드에 넣고 있을 것
                    "public_ip": r.public_ip,
                    "private_ip": r.private_ip,
                    "action": r.action,
                    "has_sensitive": r.has_sensitive,
                    "file_blocked": r.file_blocked,
                    "file_ext": ext,
                }
            )

    # 차트용 구조 정리
    ext_labels = sorted(donut_counts.keys())
    donut_data = [donut_counts[e] for e in ext_labels]

    all_entity_labels = sorted(
        {lab for ext in stacked_counts.values() for lab in ext.keys()}
    )

    matrix: List[List[int]] = []
    for ext in ext_labels:
        row = [stacked_counts[ext].get(lab, 0) for lab in all_entity_labels]
        matrix.append(row)

    return {
        "donut": {
            "labels": ext_labels,
            "data": donut_data,
        },
        "stacked": {
            "formats": ext_labels,
            "labels": all_entity_labels,
            "matrix": matrix,
        },
        "recent": recent,
    }