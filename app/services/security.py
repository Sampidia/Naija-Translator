import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Header, HTTPException, Request

from app.config import settings


class InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self.window_seconds = 60
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def check(self, key: str) -> None:
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window_seconds:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
            q.append(now)


rate_limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not settings.require_api_key:
        return
    if not settings.api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")


def enforce_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    rate_limiter.check(client)
