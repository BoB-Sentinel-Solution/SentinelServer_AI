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
    # format: 서버에서 지원하는 확장자 (예: "png", "jpg", "pdf", "docx" ...)
    format: Optional[str] = None
    # data: base64 인코딩된 파일 데이터 (요청/응답 공통)
    data: Optional[str] = None
    # 선택: 바이트 크기(응답에서 사용, 요청에서는 없어도 됨)
    size: Optional[int] = None


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
    entities: List[Entity] = Field(default_factory=list)
    processing_ms: int

    file_blocked: bool = False
    allow: bool = True
    action: str = "allow"

    # 에이전트로 보내는 "근거" 텍스트
    alert: str = ""  # 로컬 AI의 reason/설명 등을 넣어 전달

    # 레댁션/디텍션 완료된 첨부파일 (없으면 None)
    attachment: Optional[Attachment] = None
