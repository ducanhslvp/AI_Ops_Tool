from app.ai.config import ProviderConfig
from app.ai.models import (
    ChatRequest, ChatResponse, ModelInfo, ProviderCapabilities, ProviderHealth, ProviderInfo,
    ProviderStatus, ToolCall,
)
from app.ai.providers.http import HttpProvider


class GeminiProvider(HttpProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(base_url=config.base_url or "https://generativelanguage.googleapis.com/v1beta",
                         api_key=config.api_key.get_secret_value() if config.api_key else None,
                         timeout=config.timeout_seconds)
        self.model = config.model
        self._capabilities = ProviderCapabilities(tools=True, images=True, reasoning=True)

    async def health_check(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(provider="gemini", status=ProviderStatus.authentication_required)
        latency = await self._health_latency(
            self._request("GET", f"/models/{self.model}", params={"key": self.api_key})
        )
        return ProviderHealth(provider="gemini", status=ProviderStatus.ready,
                              latency_ms=latency, model=self.model)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        contents = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                parts = [{"functionResponse": {"name": message.name,
                          "response": {"result": message.content}}}]
            else:
                parts = ([{"text": message.content}] if message.content else [])
                parts.extend({"functionCall": {"name": call.name, "args": call.arguments}}
                             for call in message.tool_calls)
            contents.append({"role": "model" if message.role == "assistant" else "user",
                             "parts": parts})
        payload = {"contents": contents}
        system = "\n".join(message.content for message in request.messages if message.role == "system")
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if request.tools:
            payload["tools"] = [{"functionDeclarations": [{"name": tool.name,
                "description": tool.description, "parameters": tool.parameters}
                for tool in request.tools]}]
        data = self._json(await self._request(
            "POST", f"/models/{request.model or self.model}:generateContent",
            params={"key": self.api_key or ""}, json_body=payload))
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        calls = tuple(ToolCall(name=item["functionCall"]["name"],
                               arguments=item["functionCall"].get("args") or {})
                      for item in parts if "functionCall" in item)
        return ChatResponse(request_id=request.request_id, provider="gemini", model=self.model,
                            content="".join(item.get("text", "") for item in parts), tool_calls=calls,
                            finish_reason="tool_calls" if calls else "stop")

    def stream_chat(self, request: ChatRequest):
        return self._fallback_stream(request)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(provider="gemini", model=self.model, capabilities=self._capabilities)

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(name="gemini", display_name="Google Gemini", transport="https",
                            capabilities=self._capabilities)
