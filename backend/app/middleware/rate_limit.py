from collections import OrderedDict, deque
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int, max_clients: int = 10_000) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.max_clients = max_clients
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    async def dispatch(self, request: Request, call_next) -> Response:
        key = request.client.host if request.client else "unknown"
        now = monotonic()
        bucket = self._hits.setdefault(key, deque())
        self._hits.move_to_end(key)
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429, content={"error": {"message": "Rate limit exceeded"}}
            )
        bucket.append(now)
        while len(self._hits) > self.max_clients:
            self._hits.popitem(last=False)
        return await call_next(request)
