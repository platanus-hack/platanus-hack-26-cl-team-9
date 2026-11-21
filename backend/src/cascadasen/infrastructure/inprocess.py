"""An httpx client that calls the FastAPI app in the same process (docs/assistant.md).

The assistant uses the real routes, so validation, errors and rate limits all apply, without a network
hop. The caller's IP is presented as the peer address so per-IP limits count against the real client.
Call it from a worker thread (a `def` route): it hands each request to the event loop.
"""

from __future__ import annotations

from typing import Any

import anyio.from_thread
import httpx


class InProcessTransport(httpx.BaseTransport):
    def __init__(self, app: Any, client_ip: str) -> None:
        self.asgi = httpx.ASGITransport(app=app, client=(client_ip, 0))

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return anyio.from_thread.run(self._call, request)

    async def _call(self, request: httpx.Request) -> httpx.Response:
        response = await self.asgi.handle_async_request(request)
        body = b"".join([chunk async for chunk in response.stream])
        await response.stream.aclose()
        return httpx.Response(response.status_code, headers=response.headers, content=body, request=request)


def in_process_client(app: Any, client_ip: str) -> httpx.Client:
    """No compression (the body is read as is) and a short timeout for each call."""
    return httpx.Client(
        base_url="http://app",
        transport=InProcessTransport(app, client_ip),
        headers={"Accept-Encoding": "identity"},
        timeout=60,
    )
