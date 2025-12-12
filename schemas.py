from __future__ import annotations

from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

# --- Pydantic v2 / v1 호환 임포트 ---
try:
    from pydantic import AliasChoices, ConfigDict, model_validator  # v2
    _PYD_V2 = True
except Exception:  # v1 fallback
    _PYD_V2 = False
    AliasChoices = None  # type: ignore
    ConfigDict = None  # type: ignore
    model_validator = None  # type: ignore
    try:
        from pydantic import root_validator  # type: ignore
    except Exception:
        root_validator = None  # type: ignore


# --------------------- 공통 유틸 ---------------------
def _pc_name_field_v2():
    # PCName / pcName / pc_name 를 모두 pc_name에 매핑
    return Field(default=None, validation_alias=AliasChoices("PCName", "pcName", "pc_name"))  # type: ignore[arg-type]


def _merge_pcname_aliases(values: Dict[str, Any]) -> Dict[str, Any]:
    # 우선순위: PCName > pcName > pc_name
    v = values.get("PCName") or values.get("pcName") or values.get("pc_name")
    if v is not None and not values.get("pc_name"):
        values["pc_name"] = v
    return values


def _fill_unknown_minimum(values: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    # 서버/DB에서 nullable=False 로 쓰는 필드가 비어있으면 unknown으로 보정
    for k in keys:
        if values.get(k) is None or (isinstance(values.get(k), str) and not str(values.get(k)).strip()):
            values[k] = "unknown"
    return values


# --------------------- 기본 객체 ---------------------
class Attachment(BaseModel):
    # format: 서버에서 지원하는 확장자 (예: "png", "jpg", "pdf", "docx" ...)
    format: Optional[str] = None
    # data: base64 인코딩된 파일 데이터 (요청/응답 공통)
    data: Optional[str] = None
    # size: base64 디코딩 기준 원본 바이너리 크기 (bytes)
    #       - 요청: 에이전트가 채워서 보내는 것을 권장
    #       - 응답: 서버가 처리 결과 파일의 바이트 크기
    size: Optional[int] = None
    # 파일 내용이 원본 대비 변경되었는지(레댁션/토큰 치환 등)
    file_change: bool = False

    if _PYD_V2:
        model_config = ConfigDict(extra="ignore")  # type: ignore[misc]
    else:
        class Config:
            extra = "ignore"


# --------------------- 입력 스키마 ---------------------
class InItem(BaseModel):
    # 시간/식별
    time: str
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None

    # 호스트/호스트명
    host: Optional[str] = None
    hostname: Optional[str] = None  # 구 에이전트 필드가 그대로 들어오면 사용

    # PC 이름 (여러 별칭 허용)
    if _PYD_V2:
        pc_name: Optional[str] = _pc_name_field_v2()
        model_config = ConfigDict(populate_by_name=True, extra="ignore")  # type: ignore[misc]
    else:
        pc_name: Optional[str] = Field(default=None, alias="pc_name")

        class Config:
            allow_population_by_field_name = True
            extra = "ignore"

        if root_validator:
            @root_validator(pre=True)
            def _merge_pcname_aliases_v1(cls, values):
                return _merge_pcname_aliases(values)

    # 본문/부가
    prompt: str
    attachment: Optional[Attachment] = None
    interface: str = "llm"

    # (선택) 최소 보정: host가 없으면 서버에서 anyway "unknown" 처리하지만,
    # 여기서도 한 번 보정해두면 downstream이 편해짐
    if _PYD_V2 and model_validator:
        @model_validator(mode="before")
        @classmethod
        def _fill_minimum_v2(cls, values):
            if isinstance(values, dict):
                values = _fill_unknown_minimum(values, ["host"])
            return values
    else:
        if root_validator:
            @root_validator(pre=True)
            def _fill_minimum_v1(cls, values):
                if isinstance(values, dict):
                    values = _fill_unknown_minimum(values, ["host"])
                return values


# --------------------- 엔티티/응답 스키마 ---------------------
class Entity(BaseModel):
    value: str
    begin: int
    end: int
    label: str

    if _PYD_V2:
        model_config = ConfigDict(extra="ignore")  # type: ignore[misc]
    else:
        class Config:
            extra = "ignore"


class ServerOut(BaseModel):
    request_id: str
    host: str
    modified_prompt: str
    has_sensitive: bool
    entities: List[Entity] = Field(default_factory=list)
    processing_ms: int

    file_blocked: bool = False
    allow: bool = True
    action: str = "allow"

    # 에이전트로 보내는 "근거" 텍스트
    alert: str = ""

    # 레댁션/디텍션 완료된 첨부파일 (없으면 None)
    attachment: Optional[Attachment] = None

    if _PYD_V2:
        model_config = ConfigDict(extra="ignore")  # type: ignore[misc]
    else:
        class Config:
            extra = "ignore"


# ===================== MCP 설정 파일용 스키마 =====================
class McpInItem(BaseModel):
    """
    에이전트에서 /api/mcp 로 보내는 MCP 설정 파일 정보
    """
    time: str
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None

    # LLM 환경 / 호스트 (예: 'claude', 'chatgpt', ...)
    host: Optional[str] = None

    # PC 이름 (여러 별칭 허용)
    if _PYD_V2:
        pc_name: Optional[str] = _pc_name_field_v2()
        model_config = ConfigDict(populate_by_name=True, extra="ignore")  # type: ignore[misc]
    else:
        pc_name: Optional[str] = Field(default=None, alias="pc_name")

        class Config:
            allow_population_by_field_name = True
            extra = "ignore"

        if root_validator:
            @root_validator(pre=True)
            def _merge_pcname_aliases_v1(cls, values):
                return _merge_pcname_aliases(values)

    status: str                 # 'activate' or 'delete'
    file_path: str              # MCP 설정 파일 경로
    config_raw: Dict[str, Any] = Field(default_factory=dict)

    # ✅ DB에서 nullable=False 로 쓰는 필드가 많으니 최소 보정
    # (서버에서 바로 insert할 때 터지는 거 방지)
    if _PYD_V2 and model_validator:
        @model_validator(mode="before")
        @classmethod
        def _fill_minimum_v2(cls, values):
            if isinstance(values, dict):
                values = _merge_pcname_aliases(values)
                # host / pc_name 은 DB에서 NOT NULL인 경우가 많아서 unknown 보정
                values = _fill_unknown_minimum(values, ["host", "pc_name", "public_ip"])
            return values
    else:
        if root_validator:
            @root_validator(pre=True)
            def _fill_minimum_v1(cls, values):
                if isinstance(values, dict):
                    values = _merge_pcname_aliases(values)
                    values = _fill_unknown_minimum(values, ["host", "pc_name", "public_ip"])
                return values


class McpInResponse(BaseModel):
    """
    /api/mcp 응답: 저장 결과 요약
    """
    snapshot_id: str
    mcp_scope: str
    total_servers: int

    if _PYD_V2:
        model_config = ConfigDict(extra="ignore")  # type: ignore[misc]
    else:
        class Config:
            extra = "ignore"
