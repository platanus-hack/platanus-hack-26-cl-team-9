"""What the MCP process remembers between tool calls, so the user never repeats ids.

Held in memory only: the session id is a capability (docs/sessions-api.md section 1), so it is not
written to disk or logged.
"""

from __future__ import annotations

from dataclasses import dataclass

from cascadasen.mcp.client import ToolError


@dataclass
class McpState:
    session_id: str | None = None
    run_id: str | None = None

    def need_session(self) -> str:
        if self.session_id is None:
            raise ToolError("No hay sesión activa. Llama primero a start_session (o join_session con un id).")
        return self.session_id

    def need_run(self) -> str:
        if self.run_id is None:
            raise ToolError("No hay corrida activa. Llama primero a start_run.")
        return self.run_id
