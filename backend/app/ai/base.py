import asyncio
from collections.abc import AsyncIterator

from app.ai.errors import RequestCancelledError
from app.ai.models import ChatRequest, StreamEvent
from app.ai.provider import AIProvider


class BaseProvider(AIProvider):
    def __init__(self) -> None:
        self._initialized = False
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def initialize(self) -> None:
        self._initialized = True

    def _begin(self, request_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._cancel_events[request_id] = event
        return event

    def _finish(self, request_id: str) -> None:
        self._cancel_events.pop(request_id, None)

    def _ensure_active(self, request_id: str) -> None:
        event = self._cancel_events.get(request_id)
        if event and event.is_set():
            raise RequestCancelledError("AI request was cancelled")

    async def cancel(self, request_id: str) -> bool:
        event = self._cancel_events.get(request_id)
        if event is None:
            return False
        event.set()
        return True

    async def close(self) -> None:
        for event in self._cancel_events.values():
            event.set()
        self._cancel_events.clear()
        self._initialized = False

    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError
