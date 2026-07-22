from app.ai.config import ProviderConfig
from app.ai.models import (
    ChatRequest, ChatResponse, ModelInfo, ProviderCapabilities, ProviderHealth, ProviderInfo,
    ProviderStatus, TokenUsage, ToolCall,
)
from app.ai.providers.http import HttpProvider


class ClaudeProvider(HttpProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(base_url=config.base_url or "https://api.anthropic.com/v1",
                         api_key=config.api_key.get_secret_value() if config.api_key else None,
                         timeout=config.timeout_seconds)
        self.model = config.model
        self._capabilities = ProviderCapabilities(tools=True, images=True, reasoning=True)

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}

    async def health_check(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(provider="claude", status=ProviderStatus.authentication_required)
        return ProviderHealth(provider="claude", status=ProviderStatus.ready, model=self.model,
                              detail="Credentials configured; verified on first request")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        system = "\n".join(message.content for message in request.messages if message.role == "system")
        messages = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                messages.append({"role": "user", "content": [{"type": "tool_result",
                    "tool_use_id": message.tool_call_id, "content": message.content}]})
                continue
            content = ([{"type": "text", "text": message.content}] if message.content else [])
            content.extend({"type": "tool_use", "id": call.id, "name": call.name,
                            "input": call.arguments} for call in message.tool_calls)
            messages.append({"role": message.role, "content": content})
        payload = {"model": request.model or self.model,
                   "max_tokens": request.max_output_tokens or 2048, "messages": messages}
        if system:
            payload["system"] = system
        if request.tools:
            payload["tools"] = [{"name": tool.name, "description": tool.description,
                                 "input_schema": tool.parameters} for tool in request.tools]
        data = self._json(await self._request("POST", "/messages", headers=self._headers(),
                                              json_body=payload))
        text = "".join(item.get("text", "") for item in data.get("content", [])
                       if item.get("type") == "text")
        calls = tuple(ToolCall(id=item.get("id"), name=item["name"],
                               arguments=item.get("input") or {}) for item in data.get("content", [])
                      if item.get("type") == "tool_use")
        usage = data.get("usage") or {}
        return ChatResponse(request_id=request.request_id, provider="claude",
                            model=data.get("model", self.model), content=text, tool_calls=calls,
                            finish_reason="tool_calls" if calls else data.get("stop_reason", "stop"),
                            usage=TokenUsage(input_tokens=usage.get("input_tokens", 0),
                                             output_tokens=usage.get("output_tokens", 0)))

    def stream_chat(self, request: ChatRequest):
        return self._fallback_stream(request)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(provider="claude", model=self.model, capabilities=self._capabilities)

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(name="claude", display_name="Anthropic Claude", transport="https",
                            capabilities=self._capabilities)
