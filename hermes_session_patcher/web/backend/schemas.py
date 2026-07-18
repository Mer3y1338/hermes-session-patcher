"""Web API 数据模型"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class SessionFormatEnum(str, Enum):
    HERMES = "hermes"


class Session(BaseModel):
    session_id: str
    source: str
    model: str = ""
    title: str = ""
    message_count: int = 0
    started_at_str: str = ""
    has_refusal: bool = False
    refusal_count: int = 0
    has_backup: bool = False
    backup_count: int = 0


class SessionListResponse(BaseModel):
    sessions: List[Session]
    total: int
    refusal_count: int


class ChangeType(str, Enum):
    REPLACE = "replace"
    REMOVE_THINKING = "remove_thinking"


class ChangeDetail(BaseModel):
    message_id: int
    session_id: str
    change_type: ChangeType
    original: Optional[str] = None
    replacement: Optional[str] = None


class PreviewResponse(BaseModel):
    has_changes: bool
    changes: List[ChangeDetail]


class PatchRequest(BaseModel):
    session_id: str
    mock_response: Optional[str] = None
    clean_reasoning: bool = True
    selected_message_ids: Optional[List[int]] = None
    create_backup: bool = True


class PatchResponse(BaseModel):
    success: bool
    modified: bool
    changes: List[ChangeDetail] = []
    message: str = ""


class BackupInfo(BaseModel):
    filename: str
    session_id: Optional[str] = None
    timestamp: str
    size: int


class RestoreResponse(BaseModel):
    success: bool
    message: str


class CTFStatusResponse(BaseModel):
    installed: bool
    config_yaml: bool = False
    soul_md: bool = False


class CTFInstallRequest(BaseModel):
    mode: str = "append"


class CTFInstallResponse(BaseModel):
    success: bool
    message: str


class AIConfig(BaseModel):
    enabled: bool = False
    endpoint: str = ""
    key: str = ""
    model: str = ""


class Settings(BaseModel):
    mock_response: str = ""
    ai_config: AIConfig = Field(default_factory=AIConfig)


class AIRewriteResponse(BaseModel):
    success: bool
    rewritten: str = ""


class PromptRewriteRequest(BaseModel):
    prompt: str
