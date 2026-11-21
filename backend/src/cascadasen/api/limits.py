"""Per-process limits of the sessions API and the global runs (docs/sessions-api.md, Limits):
token-bucket rate limits, SSE connection slots, one request at a time per session and a 64 KB request body cap. With
several instances each one counts on its own, so the effective limit is per instance; across instances the store's
conditional writes and If-Match guard a session."""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException, Request

MAX_BODY_BYTES = 65536
BODY_LIMIT_PREFIXES = ("/api/v1/sessions", "/api/v1/sim/runs", "/api/v1/assistant")
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


class SessionLocks:
    """One request at a time per session: a lock per session id, dropped when no request holds or
    waits for it. A request that waits longer than `timeout_s` gets 409 with Retry-After."""

    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._locks: dict[str, list[Any]] = {}  # sid -> [Lock, requests holding or waiting]
        self._guard = threading.Lock()

    @contextmanager
    def hold(self, sid: str) -> Iterator[None]:
        with self._guard:
            entry = self._locks.setdefault(sid, [threading.Lock(), 0])
            entry[1] += 1
        got = entry[0].acquire(timeout=self.timeout_s)
        try:
            if not got:
                raise HTTPException(
                    409, "La sesión está ocupada con otra solicitud; reintenta.", headers={"Retry-After": "1"}
                )
            yield
        finally:
            if got:
                entry[0].release()
            with self._guard:
                entry[1] -= 1
                if entry[1] == 0:
                    del self._locks[sid]

    def __len__(self) -> int:
        with self._guard:
            return len(self._locks)


def client_ip(request: Request) -> str:
    """The client address for rate limits. Each trusted proxy appends the address it saw to
    X-Forwarded-For, so the client is the entry `trusted_proxy_hops` from the right (2 behind
    CloudFront and the ALB); entries further left are client-supplied and ignored. With no trusted
    proxy (0, the default) or a shorter header it is the peer address."""
    hops = request.app.state.settings.trusted_proxy_hops
    entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
    if hops > 0 and len(entries) >= hops:
        return entries[-hops]
    return request.client.host if request.client else "unknown"


class BodyLimitMiddleware:
    """ASGI middleware: 413 when a sessions or global runs request declares a body over MAX_BODY_BYTES."""

    def __init__(
        self, app: Any, max_bytes: int = MAX_BODY_BYTES, prefixes: tuple[str, ...] = BODY_LIMIT_PREFIXES
    ) -> None:
        self.app, self.max_bytes, self.prefixes = app, max_bytes, prefixes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"].startswith(self.prefixes):
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
