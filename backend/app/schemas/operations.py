from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Timestamped


class ToolDescriptor(BaseModel):
    name: str
    plugin: str
    description: str
    risk_level: str
    target_types: list[str]
    arguments_schema: dict[str, Any]


class ToolDescriptorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=3, max_length=4000)
    risk_level: str = Field(pattern="^(low|medium|high|critical)$")
    target_types: list[str] = Field(min_length=1, max_length=20)


class ToolExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_id: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=5)
    session_id: str | None = None
    approval_id: str | None = None


class ToolExecutionResponse(BaseModel):
    action: str
    server_id: str
    decision: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    command_ref: str | None = None
    approval_id: str | None = None
    confidence: dict[str, Any]


class PolicyRuleOut(Timestamped):
    name: str
    description: str
    effect: str
    priority: int
    role: str | None
    environment: str | None
    server_type: str | None
    action: str | None
    risk_level: str | None
    time_window: dict
    is_active: bool


class PolicyRuleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=4000)
    effect: str = Field(pattern="^(allow|deny|approval_required)$")
    priority: int = Field(default=100, ge=1, le=10_000)
    role: str | None = Field(default=None, max_length=80)
    environment: str | None = Field(default=None, max_length=80)
    server_type: str | None = Field(default=None, max_length=40)
    action: str | None = Field(default=None, max_length=120)
    risk_level: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    time_window: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class PolicyRuleStatusWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class PolicyRuleBulkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=200)


class ApprovalOut(Timestamped):
    requested_by_user_id: str
    server_id: str | None
    action: str
    reason: str
    impact: str
    plan: dict
    status: str
    decided_by_user_id: str | None
    decided_at: datetime | None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str = Field(min_length=3, max_length=1000)


class AiChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str | None = None
    system_id: str | None = None
    server_id: str | None = None
    message: str = Field(min_length=2, max_length=16_000)
    model: str | None = Field(default=None, max_length=160)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max", "ultra"] | None = None
    include_full_memory: bool | None = None
    internal_continuation: bool = False


class AiChatResponse(BaseModel):
    session_id: str
    request_id: str
    provider: str
    model: str
    answer: str
    plan: list[str]
    executed_tools: list[dict[str, Any]]
    confidence: dict[str, Any]


class AiSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str = Field(min_length=1, max_length=36)
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=160)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max", "ultra"] = "medium"
    include_full_memory: bool = False


class AiSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=160)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max", "ultra"] | None = None
    include_full_memory: bool | None = None


class AiProviderSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_\-]+$")


class AiCommandConsentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "reject", "accept_session", "accept_command"]
