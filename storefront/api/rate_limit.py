# SPDX-License-Identifier: Apache-2.0
"""A small, dependency-free per-IP rate limiter for one path (/api/chat by default) —
the endpoint that actually calls the Anthropic API and costs real money per request.
In-memory, so it only limits correctly with a single worker process (Render's default
WEB_CONCURRENCY=1 for this app) — fine for now; a multi-worker/multi-instance deploy
would need a shared store (e.g. Redis) instead.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _client_ip(request: Request) -> str:
    # Render (and most proxies/CDNs) put the real client IP first in
    # X-Forwarded-For; request.client.host alone would just be the proxy.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ChatRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        path: str = "/api/chat",
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        super().__init__(app)
        self.path = path
        self.max_requests = max_requests or int(os.environ.get("CHAT_RATE_LIMIT_MAX", "10"))
        self.window_seconds = window_seconds or int(
            os.environ.get("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")
        )
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path != self.path:
            return await call_next(request)

        client_ip = _client_ip(request)
        now = time.monotonic()
        hits = self._hits[client_ip]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.max_requests:
            return JSONResponse(
                {
                    "error": (
                        "You're sending messages a bit quickly — please wait a "
                        "moment and try again."
                    )
                },
                status_code=429,
            )

        hits.append(now)
        return await call_next(request)