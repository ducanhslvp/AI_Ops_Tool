from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ProviderStatus(StrEnum):
    disconnected = "disconnected"
    connecting = "connecting"
    ready = "ready"
    busy = "busy"
    degraded = "degraded"
    authentication_required = "authentication_required"


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)
    streaming: bool = False
    tools: bool = False
    images: bool = False
    reasoning: bool = False
    mcp: bool = False
    local_execution: bool = False


class ProviderInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    display_name: str
    version: str = "unknown"
    transport: str
    capabilities: ProviderCapabilities


class ModelInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str
    model: str
    version: str = "unknown"
    context_length: int | None = None
    capabilities: ProviderCapabilities


class ProviderHealth(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str
    status: ProviderStatus
    latency_ms: int | None = None
    model: str | None = None
    version: str | None = None
    detail: str | None = None


class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AIMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_tokens: int = 0
    output_tokens: int = 0


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    messages: tuple[AIMessage, ...]
    tools: tuple[ToolDefinition, ...] = ()
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, gt=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str
    provider: str
    model: str
    content: str = ""
    reasoning_summary: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str = "stop"
    usage: TokenUsage = Field(default_factory=TokenUsage)
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider_session_id: str | None = None
    provider_input: str | None = None


class StreamEventType(StrEnum):
    started = "started"
    content_delta = "content_delta"
    reasoning_delta = "reasoning_delta"
    tool_call = "tool_call"
    tool_result = "tool_result"
    completed = "completed"
    error = "error"
    cancelled = "cancelled"


class StreamEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: StreamEventType
    request_id: str
    provider: str
    delta: str | None = None
    tool_call: ToolCall | None = None
    data: dict[str, Any] = Field(default_factory=dict)
