import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.ai.base import BaseProvider
from app.ai.errors import (
    ProviderAuthenticationError,
    ProviderProtocolError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.models import ChatRequest, StreamEvent, StreamEventType


class HttpProvider(BaseProvider):
    def __init__(self, *, base_url: str, api_key: str | None, timeout: float) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        self.client = httpx.AsyncClient(timeout=self.timeout)
        await super().initialize()

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None
        await super().close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self.client is None:
            raise ProviderUnavailableError("Provider is not initialized")
        try:
            response = await self.client.request(
                method, f"{self.base_url}{path}", headers=headers, json=json_body, params=params
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError("Provider authentication failed")
        if response.status_code >= 500:
            raise ProviderUnavailableError(f"Provider returned HTTP {response.status_code}")
        if response.is_error:
            raise ProviderProtocolError(f"Provider returned HTTP {response.status_code}")
        return response

    def _fallback_stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        async def generate() -> AsyncIterator[StreamEvent]:
            yield StreamEvent(
                type=StreamEventType.started,
                request_id=request.request_id,
                provider=self.get_provider_info().name,
                data={"fallback": True},
            )
            response = await self.chat(request)
            if response.content:
                yield StreamEvent(
                    type=StreamEventType.content_delta,
                    request_id=request.request_id,
                    provider=response.provider,
                    delta=response.content,
                )
            for call in response.tool_calls:
                yield StreamEvent(
                    type=StreamEventType.tool_call,
                    request_id=request.request_id,
                    provider=response.provider,
                    tool_call=call,
                )
            yield StreamEvent(
                type=StreamEventType.completed,
                request_id=request.request_id,
                provider=response.provider,
                data={"finish_reason": response.finish_reason, "fallback": True},
            )

        return generate()

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError("Provider returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ProviderProtocolError("Provider response must be a JSON object")
        return value

    @staticmethod
    async def _health_latency(coro: Any) -> int:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await coro
        return int((loop.time() - started) * 1000)
