import json

from app.ai.config import ProviderConfig
from app.ai.models import (
    ChatRequest, ChatResponse, ModelInfo, ProviderCapabilities, ProviderHealth, ProviderInfo,
    ProviderStatus, ToolCall,
)
from app.ai.providers.http import HttpProvider


class LMStudioProvider(HttpProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(base_url=config.base_url or "http://127.0.0.1:1234/v1", api_key=None,
                         timeout=config.timeout_seconds)
        self.model = config.model
        self._capabilities = ProviderCapabilities(tools=True, local_execution=True)

    async def health_check(self) -> ProviderHealth:
        latency = await self._health_latency(self._request("GET", "/models"))
        return ProviderHealth(provider="lm_studio", status=ProviderStatus.ready,
                              latency_ms=latency, model=self.model)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        messages = []
        for message in request.messages:
            item = message.model_dump(exclude_none=True, exclude={"tool_calls", "name"})
            if message.tool_calls:
                item["tool_calls"] = [{"id": call.id, "type": "function", "function": {
                    "name": call.name, "arguments": json.dumps(call.arguments)}}
                    for call in message.tool_calls]
            messages.append(item)
        payload = {"model": request.model or self.model, "messages": messages, "stream": False}
        if request.tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": tool.name, "description": tool.description, "parameters": tool.parameters}}
                for tool in request.tools]
        data = self._json(await self._request("POST", "/chat/completions", json_body=payload))
        choice = data["choices"][0]
        message = choice["message"]
        calls = tuple(ToolCall(id=item.get("id"), name=item["function"]["name"],
                               arguments=json.loads(item["function"].get("arguments") or "{}"))
                      for item in message.get("tool_calls", []))
        return ChatResponse(request_id=request.request_id, provider="lm_studio",
                            model=data.get("model", self.model), content=message.get("content") or "",
                            tool_calls=calls, finish_reason=choice.get("finish_reason", "stop"))

    def stream_chat(self, request: ChatRequest):
        return self._fallback_stream(request)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(provider="lm_studio", model=self.model, capabilities=self._capabilities)

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(name="lm_studio", display_name="LM Studio", transport="local_http",
                            capabilities=self._capabilities)
