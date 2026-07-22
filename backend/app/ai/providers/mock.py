import asyncio
import json
import re
from collections.abc import AsyncIterator
from time import perf_counter

from app.ai.base import BaseProvider
from app.ai.models import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
    StreamEvent,
    StreamEventType,
    ToolCall,
)


class MockProvider(BaseProvider):
    def __init__(self, model: str = "mock-operations-v1", latency_ms: int = 5) -> None:
        super().__init__()
        self.model = model
        self.latency_ms = latency_ms
        self._capabilities = ProviderCapabilities(
            streaming=True, tools=True, reasoning=True, mcp=True, local_execution=True
        )

    async def health_check(self) -> ProviderHealth:
        started = perf_counter()
        await asyncio.sleep(0)
        return ProviderHealth(
            provider="mock",
            status=ProviderStatus.ready if self._initialized else ProviderStatus.disconnected,
            latency_ms=int((perf_counter() - started) * 1000),
            model=self.model,
            version="1.0",
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._begin(request.request_id)
        try:
            await asyncio.sleep(self.latency_ms / 1000)
            self._ensure_active(request.request_id)
            last = request.messages[-1].content if request.messages else ""
            tool_calls: tuple[ToolCall, ...] = ()
            lowered = last.lower()
            if request.tools and not any(message.role == "tool" for message in request.messages):
                mapping = {
                    "disk": "check_disk",
                    "cpu": "check_cpu",
                    "memory": "check_memory",
                    "ram": "check_memory",
                    "redis": "check_service",
                    "nginx": "check_service",
                    "kafka": "tail_log",
                    "oracle": "check_process",
                    "network": "check_network",
                    "restart": "restart_service",
                }
                for keyword, name in mapping.items():
                    if re.search(rf"\b{re.escape(keyword)}\b", lowered) and any(
                        tool.name == name for tool in request.tools
                    ):
                        arguments: dict[str, object] = {}
                        if name in {"restart_service", "check_service"}:
                            arguments["service"] = "redis-server" if keyword == "redis" else "nginx"
                        if name == "tail_log":
                            arguments = {"path": "/var/log/kafka/consumer.log", "lines": 100}
                        tool_calls = (ToolCall(name=name, arguments=arguments),)
                        break
            tool_messages = [message for message in request.messages if message.role == "tool"]
            tool_failed = any('"error"' in message.content for message in tool_messages)
            if tool_failed:
                content = "The requested diagnostic did not run. More target or approval data is required."
            elif tool_messages:
                content = self._summarize_tool_result(tool_messages[-1].content)
            elif tool_calls:
                content = "I will request the required diagnostic through the backend Tool Registry."
            else:
                content = "I can analyze this safely using provider-neutral AIOps tools."
            return ChatResponse(
                request_id=request.request_id,
                provider="mock",
                model=self.model,
                content=content,
                reasoning_summary="Selected only registered backend capabilities.",
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                confidence=0.35 if tool_failed else (0.9 if tool_messages else 0.72),
            )
        finally:
            self._finish(request.request_id)

    def _summarize_tool_result(self, content: str) -> str:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return "Diagnostic output was received but could not be classified."
        output = str(payload.get("stdout") or payload.get("stderr") or "")
        lowered = output.lower()
        if "100%" in output or " 97%" in output:
            return (
                "Disk utilization is critical: the root or data filesystem has almost no "
                "free capacity. Collect large-file evidence before any approved cleanup."
            )
        if "94.7 us" in output or "187.4" in output:
            return (
                "CPU saturation is confirmed. Application worker processes dominate CPU; "
                "capture a second sample and inspect the affected workload before changes."
            )
        if "swap:" in lowered and "1988" in output:
            return (
                "Memory pressure is critical and swap is nearly exhausted. The Java process "
                "is the leading leak candidate; more heap evidence is required."
            )
        if "redis-server.service" in lowered and "failed" in lowered:
            return (
                "Redis is unavailable because its service failed to bind port 6379. Verify the "
                "existing listener before requesting a restart."
            )
        if "nginx.service" in lowered and "failed" in lowered:
            return (
                "Nginx is down because configuration validation cannot resolve an upstream. "
                "Correct and validate the upstream configuration before restart approval."
            )
        if "total_lag=" in lowered:
            return (
                "Kafka consumer lag is high and increasing. Processing latency and broker queue "
                "time should be investigated before scaling or restarting consumers."
            )
        if "ora_p003_erp" in lowered:
            return (
                "Oracle database processes are consuming sustained CPU, consistent with a slow "
                "parallel workload. Correlate the session and wait-event evidence before action."
            )
        if "network is unreachable" in lowered:
            return (
                "The target interface is up, but packet errors and an unreachable upstream route "
                "confirm a network-path failure. Routing and link evidence are required."
            )
        if payload.get("exit_code") not in {0, None}:
            return "The diagnostic returned a failure status. Additional target evidence is required."
        return "The controlled diagnostic completed successfully and shows no critical signal."

    async def tool_call(self, request: ChatRequest, tool_call: ToolCall) -> ChatResponse:
        return await self.chat(request)

    async def _stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        response = await self.chat(request)
        yield StreamEvent(
            type=StreamEventType.started,
            request_id=request.request_id,
            provider="mock",
            data={"model": self.model},
        )
        for call in response.tool_calls:
            yield StreamEvent(
                type=StreamEventType.tool_call,
                request_id=request.request_id,
                provider="mock",
                tool_call=call,
            )
        for word in response.content.split(" "):
            yield StreamEvent(
                type=StreamEventType.content_delta,
                request_id=request.request_id,
                provider="mock",
                delta=f"{word} ",
            )
            await asyncio.sleep(0)
        yield StreamEvent(
            type=StreamEventType.completed,
            request_id=request.request_id,
            provider="mock",
            data={"confidence": response.confidence, "finish_reason": response.finish_reason},
        )

    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(request)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            provider="mock", model=self.model, version="1.0", context_length=32_000,
            capabilities=self._capabilities,
        )

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="mock", display_name="Offline Mock", version="1.0", transport="in_process",
            capabilities=self._capabilities,
        )
