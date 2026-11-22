"""`ToolBox` over `Sub50Tools` for the in-app assistant (docs/assistant.md)."""

from __future__ import annotations

import logging
from typing import Any

from cascadasen.domain.ports import ToolCall, ToolSpec
from cascadasen.mcp.client import ToolError
from cascadasen.mcp.specs import tool_specs
from cascadasen.mcp.tools import DEFAULT_POINT, Sub50Tools

log = logging.getLogger(__name__)

# end_session is destructive (the web had its own delete button). The session edits and cuts are left out too:
# the web does not show sessions (#101) and draws only the grid of prepare_scenario, so a datacenter added with
# add_datacenter never reached the map. The assistant puts points, cuts and changes through prepare_scenario.
# The MCP server (docs/mcp.md) still offers every tool.
EXCLUDED = frozenset(
    {
        "end_session",
        "join_session",
        "add_datacenter",
        "add_generator",
        "add_substation",
        "add_line",
        "add_bus",
        "edit_element",
        "remove_element",
        "reset_network",
        "cut_lines",
        "repair_lines",
        "get_grid_state",
    }
)
NO_SESSION_NEEDED = frozenset(
    {"start_session", "join_session", "list_options", "prepare_scenario", "find_line"}
)
NEEDS_RUN = frozenset({"inject_event", "submit_action"})  # a run is opened for them when none is active
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
        if self.defers_session(call.name, args):
            return True, {
                "deferred": True,
                "point": DEFAULT_POINT,
                "nota": "No hace falta abrir una sesión: prepare_scenario no la usa y la sesión se abre sola "
                "cuando una herramienta la necesita.",
            }
        if call.name == "step" and isinstance(args.get("cycles"), int):
            args["cycles"] = min(args["cycles"], MAX_STEP_CYCLES)
        try:
            notes = []
            if call.name not in NO_SESSION_NEEDED and self.tools.state.session_id is None:
                self.tools.start_session()  # the user cannot call start_session: open one on first need
                notes.append("Se creó una sesión nueva automáticamente para esta conversación.")
            if call.name in NEEDS_RUN and self.tools.state.run_id is None:
                run = self.tools.start_run()  # an event before start_run would be lost on the retry
                notes.append(
                    f"No había corrida activa: se creó la corrida {run['run_id']} (open_field, política "
                    f"{run['policy']}) y el evento quedó en ella. No llames a start_run de nuevo; usa step."
                )
            result = getattr(self.tools, call.name)(**args)
            if notes:
                result = {**result, "nota": " ".join(notes)}
            return True, result
        except ToolError as exc:
            return False, {"error": str(exc)}
        except TypeError:
            return False, {"error": f"Argumentos inválidos para {call.name}."}
        except Exception as exc:
            log.warning("assistant tool %s failed (%s)", call.name, type(exc).__name__)
            return False, {"error": f"Falló la herramienta {call.name}."}

    def defers_session(self, name: str, args: dict[str, Any]) -> bool:
        """A first start_session at the default point waits: the model opened one before every map change, which
        prepare_scenario never uses, and each counted against the per-IP creation limit. A tool that needs a session
        opens it on first use; another operating point (an incident's) still opens one now."""
        return (
            name == "start_session"
            and self.tools.state.session_id is None
            and args.get("point") in (None, "", DEFAULT_POINT)
        )

    def context(self) -> dict[str, str | None]:
        return {"session_id": self.tools.state.session_id, "run_id": self.tools.state.run_id}
