"""`ToolBox` over `Sub50Tools` for the in-app assistant (docs/assistant.md)."""

from __future__ import annotations

import logging
from typing import Any

from cascadasen.domain.ports import ToolCall, ToolSpec
from cascadasen.mcp.client import ToolError
from cascadasen.mcp.specs import tool_specs
from cascadasen.mcp.tools import Sub50Tools

log = logging.getLogger(__name__)

EXCLUDED = frozenset({"end_session"})  # destructive: the web has its own delete button
NO_SESSION_NEEDED = frozenset({"start_session", "join_session", "list_options"})
MAX_STEP_CYCLES = 24  # a step of many cycles can outlast the request deadline


class SessionTools:
    def __init__(self, tools: Sub50Tools, exclude: frozenset[str] = EXCLUDED) -> None:
        self.tools, self.exclude = tools, exclude
        self._specs = tool_specs(tools, exclude)
        self.names = {s.name for s in self._specs}

    def specs(self) -> list[ToolSpec]:
        return self._specs

    def run(self, call: ToolCall) -> tuple[bool, dict[str, Any]]:
        if call.name not in self.names:
            return False, {"error": f"Herramienta desconocida: {call.name}"}
        args = dict(call.arguments)
        if call.name == "step" and isinstance(args.get("cycles"), int):
            args["cycles"] = min(args["cycles"], MAX_STEP_CYCLES)
        try:
            started = call.name not in NO_SESSION_NEEDED and self.tools.state.session_id is None
            if started:  # the user cannot call start_session: open one the first time a tool needs it
                self.tools.start_session()
            result = getattr(self.tools, call.name)(**args)
            if started:
                result = {
                    **result,
                    "nota": "Se creó una sesión nueva automáticamente para esta conversación.",
                }
            return True, result
        except ToolError as exc:
            return False, {"error": str(exc)}
        except TypeError:
            return False, {"error": f"Argumentos inválidos para {call.name}."}
        except Exception as exc:
            log.warning("assistant tool %s failed (%s)", call.name, type(exc).__name__)
            return False, {"error": f"Falló la herramienta {call.name}."}

    def context(self) -> dict[str, str | None]:
        return {"session_id": self.tools.state.session_id, "run_id": self.tools.state.run_id}
