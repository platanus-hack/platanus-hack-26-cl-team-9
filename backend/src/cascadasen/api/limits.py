"""Per-process limits of the sessions API (docs/sessions-api.md, Limits): token-bucket rate limits,
SSE connection slots and a 64 KB request body cap. With several instances each one counts on its
own, so the effective limit is per instance."""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request

MAX_BODY_BYTES = 65536
BODY_LIMIT_PREFIX = "/api/v1/sessions"
MAX_BUCKETS = 10000


class TokenBucket:
    """`per` requests per `window_s` seconds for each (name, key), refilled continuously."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._buckets: dict[tuple[str, str], tuple[float, float, float]] = {}  # tokens, at, full_after
        self._lock = threading.Lock()

    def check(self, name: str, key: str, per: int, window_s: float) -> None:
        rate, now = per / window_s, self.clock()
        with self._lock:
            if len(self._buckets) > MAX_BUCKETS:  # drop buckets that refilled; they hold no state
                self._buckets = {k: v for k, v in self._buckets.items() if v[2] > now}
            tokens, at, _ = self._buckets.get((name, key), (float(per), now, now))
            tokens = min(float(per), tokens + (now - at) * rate)
            if tokens < 1:
                retry = max(1, math.ceil((1 - tokens) / rate))
                raise HTTPException(
                    429,
                    f"Demasiadas solicitudes; reintenta en {retry} s.",
                    headers={"Retry-After": str(retry)},
                )
            tokens -= 1
            self._buckets[(name, key)] = (tokens, now, now + (per - tokens) / rate)


class SseSlots:
    """Open SSE streams per key (session and client IP)."""

    def __init__(self) -> None:
        self._open: dict[Any, int] = {}
        self._lock = threading.Lock()

    def acquire(self, key: Any, limit: int) -> bool:
        with self._lock:
            if self._open.get(key, 0) >= limit:
                return False
            self._open[key] = self._open.get(key, 0) + 1
            return True

    def release(self, key: Any) -> None:
        with self._lock:
            left = self._open.get(key, 0) - 1
            if left > 0:
                self._open[key] = left
            else:
                self._open.pop(key, None)


def client_ip(request: Request) -> str:
    """The first X-Forwarded-For entry (CloudFront/ALB put the client first), else the peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


class BodyLimitMiddleware:
    """ASGI middleware: 413 when a sessions request declares a body over MAX_BODY_BYTES."""

    def __init__(self, app: Any, max_bytes: int = MAX_BODY_BYTES, prefix: str = BODY_LIMIT_PREFIX) -> None:
        self.app, self.max_bytes, self.prefix = app, max_bytes, prefix

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"].startswith(self.prefix):
            length = dict(scope.get("headers") or []).get(b"content-length")
            if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
                body = json.dumps(
                    {"detail": f"Cuerpo demasiado grande (máximo {self.max_bytes // 1024} KB)."}
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
