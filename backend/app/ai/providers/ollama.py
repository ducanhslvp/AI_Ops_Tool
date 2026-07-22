from app.ai.config import ProviderConfig
from app.ai.models import (
    ChatRequest, ChatResponse, ModelInfo, ProviderCapabilities, ProviderHealth, ProviderInfo,
    ProviderStatus, ToolCall,
)
from app.ai.providers.http import HttpProvider


class OllamaProvider(HttpProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(base_url=config.base_url or "http://127.0.0.1:11434", api_key=None,
                         timeout=config.timeout_seconds)
        self.model = config.model
        self._capabilities = ProviderCapabilities(tools=True, local_execution=True)

    async def health_check(self) -> ProviderHealth:
        latency = await self._health_latency(self._request("GET", "/api/tags"))
        return ProviderHealth(provider="ollama", status=ProviderStatus.ready,
                              latency_ms=latency, model=self.model)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        messages = []
        for message in request.messages:
            item = message.model_dump(exclude_none=True, exclude={"tool_calls"})
            if message.tool_calls:
                item["tool_calls"] = [{"type": "function", "function": {
                    "name": call.name, "arguments": call.arguments}} for call in message.tool_calls]
            messages.append(item)
        payload = {"model": request.model or self.model,
                   "messages": messages,
                   "stream": False}
        if request.tools:
            payload["tools"] = [{"type": "function", "function": {"name": tool.name,
                "description": tool.description, "parameters": tool.parameters}}
                for tool in request.tools]
        data = self._json(await self._request("POST", "/api/chat", json_body=payload))
        message = data.get("message") or {}
        calls = tuple(ToolCall(name=item["function"]["name"],
                               arguments=item["function"].get("arguments") or {})
                      for item in message.get("tool_calls", []))
        return ChatResponse(request_id=request.request_id, provider="ollama", model=self.model,
                            content=message.get("content", ""), tool_calls=calls,
                            finish_reason="tool_calls" if calls else data.get("done_reason", "stop"))

    def stream_chat(self, request: ChatRequest):
        return self._fallback_stream(request)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(provider="ollama", model=self.model, capabilities=self._capabilities)

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(name="ollama", display_name="Ollama", transport="local_http",
                            capabilities=self._capabilities)
