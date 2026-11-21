"""HTTP client of the Sub50 agent API for the MCP server (docs/mcp.md).

It only speaks HTTP to `/api/v1`: it imports nothing from the domain. Failures become `ToolError`
with the Spanish `detail` the API returned, so the model can read what to fix (including the `valid`
list of simulator input errors).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:8000"
AGENT_NAME = "mcp"


class ToolError(Exception):
    """A tool failed in a way the model can act on; the message is shown to it as is."""


def describe_detail(detail: Any) -> str:
    """Flatten the API's `detail` (string, `{field, message, valid}` or FastAPI's list)."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        text = f"{detail.get('field', 'entrada')}: {detail.get('message', detail)}"
        if detail.get("valid"):
            text += f" Valores válidos: {detail['valid']}"
        return text
    if isinstance(detail, list):
        return "; ".join(f"{'.'.join(str(p) for p in d.get('loc', []))}: {d.get('msg')}" for d in detail)
    return str(detail)


class Sub50Client:
    def __init__(
        self,
        base_url: str | None = None,
        agent: str | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        base = (base_url or os.environ.get("SUB50_API_URL") or DEFAULT_URL).rstrip("/")
        self.agent = (agent or os.environ.get("SUB50_AGENT") or AGENT_NAME)[:64]
        self.http = http or httpx.Client(base_url=base, timeout=60)
        self.api = "/api/v1"

    def request(self, method: str, path: str, body: Any = None, params: dict[str, Any] | None = None) -> Any:
        """One call. A 409 (another instance won the write) is retried once, as the API asks."""
        for attempt in (0, 1):
            try:
                r = self.http.request(
                    method,
                    self.api + path,
                    json=body,
                    params=params,
                    headers={"X-Sub50-Agent": self.agent},
                )
            except httpx.HTTPError as exc:
                raise ToolError(f"No se pudo llamar a la API de Sub50 ({type(exc).__name__}).") from exc
            if r.status_code == 409 and attempt == 0 and method != "GET":
                continue
            break
        if r.status_code == 204:
            return None
        if r.status_code == 429:
            wait = r.headers.get("Retry-After", "unos")
            raise ToolError(f"Límite de uso alcanzado: espera {wait} segundos y vuelve a intentar.")
        if r.is_error:
            try:
                detail = describe_detail(r.json().get("detail"))
            except ValueError:
                detail = r.text[:200]
            raise ToolError(f"La API respondió {r.status_code}: {detail}")
        return r.json()

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params or None)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body if body is not None else {})

    def patch(self, path: str, body: Any) -> Any:
        return self.request("PATCH", path, body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
