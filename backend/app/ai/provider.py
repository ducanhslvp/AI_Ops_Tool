from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.ai.models import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
    ProviderHealth,
    ProviderInfo,
    StreamEvent,
    ToolCall,
)


class AIProvider(ABC):
    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    async def tool_call(self, request: ChatRequest, tool_call: ToolCall) -> ChatResponse:
        raise NotImplementedError("Provider does not support an explicit tool result turn")

    @abstractmethod
    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]: ...

    @abstractmethod
    async def cancel(self, request_id: str) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def get_model_info(self) -> ModelInfo: ...

    @abstractmethod
    def get_provider_info(self) -> ProviderInfo: ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self.get_provider_info().capabilities

    def supports_stream(self) -> bool:
        return self.capabilities.streaming

    def supports_tools(self) -> bool:
        return self.capabilities.tools

    def supports_images(self) -> bool:
        return self.capabilities.images

    def supports_reasoning(self) -> bool:
        return self.capabilities.reasoning

    def supports_mcp(self) -> bool:
        return self.capabilities.mcp

    def supports_local_execution(self) -> bool:
        return self.capabilities.local_execution
