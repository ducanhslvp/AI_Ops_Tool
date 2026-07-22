import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from app.ai.errors import AIAdapterError, RequestCancelledError
from app.ai.manager import ProviderManager
from app.ai.models import (
    AIMessage, ChatRequest, ChatResponse, StreamEvent, StreamEventType, ToolCall, ToolDefinition,
)

ToolExecutor = Callable[[ToolCall], Awaitable[dict]]
ProgressCallback = Callable[[str, dict], Awaitable[None]]


@dataclass(frozen=True)
class GatewayResult:
    response: ChatResponse
    tool_events: tuple[dict, ...]
    provider_inputs: tuple[str, ...]


class AIGateway:
    """The only application-facing entry point to AI providers."""

    def __init__(self, manager: ProviderManager) -> None:
        self.manager = manager

    async def chat(
        self,
        request: ChatRequest,
        *,
        tool_executor: ToolExecutor | None = None,
        progress: ProgressCallback | None = None,
    ) -> GatewayResult:
        messages = list(request.messages)
        tool_events: list[dict] = []
        response: ChatResponse | None = None
        provider_inputs: list[str] = []
        max_tool_calls = self.manager.config.max_tool_rounds if self.manager.config else 1
        tool_call_count = 0
        for round_index in range(max_tool_calls + 1):
            current = request.model_copy(update={"messages": tuple(messages)})
            if progress:
                await progress("provider_started", {"round": round_index + 1})
            response = await self.manager.chat(current, progress=progress)
            provider_inputs.append(response.provider_input or _request_snapshot(current))
            if progress:
                await progress("provider_completed", {
                    "round": round_index + 1, "provider": response.provider,
                    "model": response.model, "tool_call_count": len(response.tool_calls),
                })
            if response.provider_session_id:
                request = request.model_copy(update={
                    "metadata": {**request.metadata,
                                 "provider_session_id": response.provider_session_id}
                })
            if not response.tool_calls:
                return GatewayResult(response=response, tool_events=tuple(tool_events),
                                     provider_inputs=tuple(provider_inputs))
            if tool_executor is None:
                break
            if tool_call_count + len(response.tool_calls) > max_tool_calls:
                raise AIAdapterError(
                    f"AI exceeded the controlled limit of {max_tool_calls} tool calls"
                )
            messages.append(AIMessage(role="assistant", content=response.content,
                                      tool_calls=response.tool_calls))
            for call in response.tool_calls:
                tool_call_count += 1
                if progress:
                    await progress("tool_call", {"id": call.id, "tool": call.name,
                                                  "arguments": call.arguments})
                result = await tool_executor(call)
                event = {"id": call.id, "tool": call.name, "arguments": call.arguments,
                         "result": result}
                tool_events.append(event)
                if progress:
                    await progress("tool_result", event)
                messages.append(AIMessage(role="tool", name=call.name, tool_call_id=call.id,
                                          content=_safe_tool_result(result)))
        if response is None:
            raise AIAdapterError("AI provider returned no response")
        return GatewayResult(response=response, tool_events=tuple(tool_events),
                             provider_inputs=tuple(provider_inputs))

    async def stream(
        self,
        request: ChatRequest,
        *,
        tool_executor: ToolExecutor | None = None,
    ) -> AsyncIterator[StreamEvent]:
        provider = self.manager.active
        try:
            if provider.supports_stream():
                async for event in provider.stream_chat(request):
                    yield event
                return
            result = await self.chat(request, tool_executor=tool_executor)
            yield StreamEvent(type=StreamEventType.started, request_id=request.request_id,
                              provider=result.response.provider, data={"fallback": True})
            for event in result.tool_events:
                yield StreamEvent(type=StreamEventType.tool_result, request_id=request.request_id,
                                  provider=result.response.provider, data=event)
            yield StreamEvent(type=StreamEventType.content_delta, request_id=request.request_id,
                              provider=result.response.provider, delta=result.response.content)
            yield StreamEvent(type=StreamEventType.completed, request_id=request.request_id,
                              provider=result.response.provider,
                              data={"finish_reason": result.response.finish_reason,
                                    "confidence": result.response.confidence, "fallback": True})
        except RequestCancelledError:
            yield StreamEvent(type=StreamEventType.cancelled, request_id=request.request_id,
                              provider=self.manager.active_name)
        except Exception as exc:
            yield StreamEvent(type=StreamEventType.error, request_id=request.request_id,
                              provider=self.manager.active_name,
                              data={"message": _public_error(exc)})

    async def cancel(self, request_id: str) -> bool:
        return await self.manager.cancel(request_id)

    async def health(self):
        return await self.manager.health()

    def providers(self) -> list[dict]:
        return self.manager.provider_info()

    async def switch_provider(self, name: str) -> None:
        await self.manager.switch(name)

    async def reload(self) -> None:
        await self.manager.reload()


def tool_definitions(registry, tools=None) -> tuple[ToolDefinition, ...]:
    definitions = []
    for tool in tools if tools is not None else registry.all():
        properties = dict(tool.arguments_schema)
        definitions.append(ToolDefinition(
            name=tool.name,
            description=tool.description,
            parameters={"type": "object", "properties": properties,
                        "required": list(properties), "additionalProperties": False},
        ))
    return tuple(definitions)


def _safe_tool_result(result: dict) -> str:
    import json

    allowed = {key: value for key, value in result.items()
               if key in {"action", "decision", "stdout", "stderr", "exit_code", "approval_id",
                          "server_id", "confidence", "error"}}
    return json.dumps(allowed, ensure_ascii=True, default=str)[:100_000]


def _request_snapshot(request: ChatRequest) -> str:
    """Provider-neutral representation used when an adapter cannot expose its wire input."""
    return json.dumps({
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "tools": [tool.model_dump(mode="json") for tool in request.tools],
        "model": request.model,
        "metadata": request.metadata,
    }, ensure_ascii=True, default=str, indent=2)


def _public_error(exc: Exception) -> str:
    if isinstance(exc, AIAdapterError):
        return exc.message
    if isinstance(exc, asyncio.TimeoutError):
        return "AI request timed out"
    return "AI provider request failed"
