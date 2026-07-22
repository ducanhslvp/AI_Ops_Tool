import json
from typing import Any

from app.ai.config import ProviderConfig
from app.ai.models import (
    ChatRequest, ChatResponse, ModelInfo, ProviderCapabilities, ProviderHealth, ProviderInfo,
    ProviderStatus, TokenUsage, ToolCall,
)
from app.ai.providers.http import HttpProvider


class OpenAIProvider(HttpProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(
            base_url=config.base_url or "https://api.openai.com/v1",
            api_key=config.api_key.get_secret_value() if config.api_key else None,
            timeout=config.timeout_seconds,
        )
        self.model = config.model
        self._capabilities = ProviderCapabilities(
            streaming=False, tools=True, images=True, reasoning=True
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def health_check(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(provider="openai", status=ProviderStatus.authentication_required)
        latency = await self._health_latency(self._request("GET", "/models", headers=self._headers()))
        return ProviderHealth(
            provider="openai", status=ProviderStatus.ready, latency_ms=latency, model=self.model
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        inputs: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "tool":
                inputs.append({"type": "function_call_output", "call_id": message.tool_call_id,
                               "output": message.content})
                continue
            if message.content:
                inputs.append({"role": message.role, "content": message.content})
            for call in message.tool_calls:
                inputs.append({"type": "function_call", "call_id": call.id, "name": call.name,
                               "arguments": json.dumps(call.arguments)})
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "input": inputs,
        }
        if request.tools:
            payload["tools"] = [
                {"type": "function", "name": tool.name, "description": tool.description,
                 "parameters": tool.parameters, "strict": True}
                for tool in request.tools
            ]
        response = self._json(
            await self._request("POST", "/responses", headers=self._headers(), json_body=payload)
        )
        content: list[str] = []
        calls: list[ToolCall] = []
        for item in response.get("output", []):
            if item.get("type") == "function_call":
                raw_args = item.get("arguments") or "{}"
                calls.append(ToolCall(id=item.get("call_id") or item.get("id"), name=item["name"],
                                      arguments=json.loads(raw_args)))
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    content.append(part.get("text", ""))
        usage = response.get("usage") or {}
        return ChatResponse(
            request_id=request.request_id, provider="openai", model=response.get("model", self.model),
            content="".join(content), tool_calls=tuple(calls),
            finish_reason="tool_calls" if calls else "stop",
            usage=TokenUsage(input_tokens=usage.get("input_tokens", 0),
                             output_tokens=usage.get("output_tokens", 0)),
        )

    def stream_chat(self, request: ChatRequest):
        return self._fallback_stream(request)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(provider="openai", model=self.model, capabilities=self._capabilities)

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(name="openai", display_name="OpenAI", transport="https",
                            capabilities=self._capabilities)
