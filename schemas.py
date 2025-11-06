# schemas.py
from __future__ import annotations
from typing import Optional, List

from pydantic import BaseModel, Field

# --- Pydantic v2 / v1 호환 임포트 ---
try:
    from pydantic import AliasChoices, ConfigDict  # v2
    _PYD_V2 = True
except Exception:  # v1 fallback
    _PYD_V2 = False
    # v1에서만 필요
    try:
        from pydantic import root_validator  # type: ignore
    except Exception:
        root_validator = None  # type: ignore


# --------------------- 기본 객체 ---------------------
class Attachment(BaseModel):
    format: Optional[str] = None   # MIME type (e.g., "image/png", "application/pdf")
    data:   Optional[str] = None   # base64 (운영에서는 저장 지양)


# --------------------- 입력 스키마 ---------------------
class InItem(BaseModel):
    # 시간/식별
    time: str                                  # ISO8601 or any string
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None

    # 호스트/호스트명
    host: Optional[str] = None                 # 대상 서비스 호스트 (예: chatgpt.com)
    hostname: Optional[str] = None             # 구 에이전트 필드(직접 들어오면 사용)

    # 에이전트가 보내는 PC 이름(여러 별칭 허용)
    if _PYD_V2:
        # v2: validation_alias + model_config
        pc_name: Optional[str] = Field(
            default=None,
            validation_alias=AliasChoices("PCName", "pcName", "pc_name"),
        )
        # 이름으로도 채우기 허용 + 알 수 없는 키는 무시
        model_config = ConfigDict(populate_by_name=True, extra="ignore")
    else:
        # v1: 여러 별칭을 root_validator(pre=True)로 병합
        pc_name: Optional[str] = Field(default=None, alias="pc_name")

        class Config:
            allow_population_by_field_name = True
            extra = "ignore"

        if root_validator:
            @root_validator(pre=True)
            def _merge_pcname_aliases(cls, values):
                # 우선순위: PCName > pcName > pc_name
                v = values.get("PCName") or values.get("pcName") or values.get("pc_name")
                if v is not None:
                    values["pc_name"] = v
                return values

    # 본문/부가
    prompt: str
    attachment: Optional[Attachment] = None
    interface: str = "llm"


# --------------------- 엔티티/응답 스키마 ---------------------
class Entity(BaseModel):
    value: str
    begin: int
    end: int
    label: str


class ServerOut(BaseModel):
    request_id: str
    host: str
    modified_prompt: str
    has_sensitive: bool
    # 가변 기본값은 default_factory 사용
    entities: List[Entity] = Field(default_factory=list)
    processing_ms: int

    file_blocked: bool = False
    allow: bool = True
    action: str = "allow"
