"""`ToolBox` over `Sub50Tools` for the in-app assistant (docs/assistant.md)."""

from __future__ import annotations

import logging
import re
from typing import Any

from cascadasen.domain.ports import ToolCall, ToolSpec
from cascadasen.mcp.client import ToolError
from cascadasen.mcp.specs import tool_specs
from cascadasen.mcp.tools import Sub50Tools

log = logging.getLogger(__name__)

EXCLUDED = frozenset({"end_session"})  # destructive: the web has its own delete button
NO_SESSION_NEEDED = frozenset({"start_session", "join_session", "list_options", "prepare_scenario"})
NEEDS_RUN = frozenset({"inject_event", "submit_action"})  # a run is opened for them when none is active
MAX_STEP_CYCLES = 24  # a step of many cycles can outlast the request deadline
USER_SIZED = frozenset({"add_datacenter", "add_generator"})  # their MW must come from the user


def numbers(text: str) -> set[float]:
    """Numbers the user wrote: "120", "1.200" or "1,5" (Spanish separators), "0.5"."""
    found = set()
    for raw in re.findall(r"\d+(?:[.,]\d+)*", text):
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):  # 1.200 -> 1200
            raw = raw.replace(".", "")
        try:
            found.add(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return found


def stated(mw: Any, said: str) -> bool:
    """`mw` (or its value in GW) appears among the numbers the user wrote."""
    try:
        value = float(mw)
    except (TypeError, ValueError):
        return False
    return any(abs(value - n) < 1e-6 or abs(value - n * 1000) < 1e-6 for n in numbers(said))


class SessionTools:
    def __init__(
        self, tools: Sub50Tools, exclude: frozenset[str] = EXCLUDED, said: str | None = None
    ) -> None:
        self.tools, self.exclude, self.said = tools, exclude, said
        self._specs = tool_specs(tools, exclude)
        self.names = {s.name for s in self._specs}

    def specs(self) -> list[ToolSpec]:
        return self._specs

    def run(self, call: ToolCall) -> tuple[bool, dict[str, Any]]:
        if call.name not in self.names:
            return False, {"error": f"Herramienta desconocida: {call.name}"}
        args = dict(call.arguments)
        if call.name in USER_SIZED and self.said is not None and not stated(args.get("mw"), self.said):
            return False, {
                "error": f"El usuario no indicó {args.get('mw')} MW. No elijas la potencia: pregúntale "
                "cuántos MW quiere y espera su respuesta."
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

    def context(self) -> dict[str, str | None]:
        return {"session_id": self.tools.state.session_id, "run_id": self.tools.state.run_id}
