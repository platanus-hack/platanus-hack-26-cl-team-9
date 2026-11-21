"""The tools the MCP server exposes (docs/mcp.md section 3).

Each method is one tool: the docstring is the description the model reads, the signature is its
schema. Tools take names or ids and return compact summaries (`digest.py`). `OPERATIONS` says which
agent-API operationIds each tool uses; a test checks they exist in `docs/openapi/agents.openapi.json`.

Guardrails (docs/cyber.md section 8): there is no tool that searches, ranks or suggests the worst
cut, and `cut_lines` takes 1 to 3 lines, as the API does. Results carry the scenario notice.
"""

from __future__ import annotations

from typing import Any, Literal

from cascadasen.mcp import digest
from cascadasen.mcp.client import Sub50Client, ToolError
from cascadasen.mcp.state import McpState

OPERATIONS: dict[str, tuple[str, ...]] = {
    "start_session": ("create_session",),
    "join_session": ("get_session",),
    "end_session": ("delete_session",),
    "list_options": ("get_catalog",),
    "describe_network": ("get_session_network",),
    "add_datacenter": ("get_session_network", "add_load"),
    "add_generator": ("get_session_network", "add_generator"),
    "add_line": ("add_line",),
    "add_bus": ("add_bus",),
    "edit_element": ("update_bus", "update_line", "update_load", "update_generator"),
    "remove_element": ("delete_bus", "delete_line", "delete_load", "delete_generator"),
    "reset_network": ("reset_session",),
    "cut_lines": ("cut_lines",),
    "repair_lines": ("repair_lines",),
    "get_grid_state": ("get_cut_state",),
    "start_run": ("create_run",),
    "inject_event": ("inject_run_event",),
    "step": ("step_run",),
    "submit_action": ("submit_run_action",),
    "run_status": ("get_run",),
    "run_report": ("get_run_report",),
    "after_action": ("get_run_after_action",),
    "replay": ("replay_run",),
}
TOOLS = tuple(OPERATIONS)

INSTRUCTIONS = """\
Sub50 simulates the consequences of events on the Chilean national grid (188 buses, 13 operating areas).
Work in this order: start_session (or join_session), describe_network to learn areas and ids, edit the
network (add_datacenter, add_generator, add_line, edit_element) and/or open lines with cut_lines, then
read the result. For strategic experiments use start_run, inject_event, step, run_report and after_action.
Use list_options for valid event, action, policy and template ids.

Rules. Every scenario is hypothetical: always say that Sub50 models the effect of an event, never the
attack technique, and describe effects and prevention only. Do not look for the line or area whose loss
does the most damage, and do not try every line to compare them: the tools do not rank targets and the
API rate-limits cuts. Values the model adds (redispatch, costs, thresholds) are assumptions; say so.
Answer in the user's language; the results are in Spanish.
"""

ELEMENT_ROUTES = {"B": "buses", "R": "lines", "U": "lines", "D": "loads", "G": "generators"}


class Sub50Tools:
    def __init__(self, client: Sub50Client, state: McpState | None = None) -> None:
        self.client = client
        self.state = state or McpState()

    # -- helpers -----------------------------------------------------------------------------

    def _base(self) -> str:
        return f"/sessions/{self.state.need_session()}"

    def _run(self) -> str:
        return f"{self._base()}/runs/{self.state.need_run()}"

    def _network(self) -> dict[str, Any]:
        return self.client.get(f"{self._base()}/network")

    def _element_path(self, element_id: str) -> str:
        route = ELEMENT_ROUTES.get(element_id[:1].upper())
        if route is None or len(element_id) < 2:
            raise ToolError(
                f"'{element_id}' no es un id de elemento. Usa B### (barra), R###/U### (línea), "
                "D### (carga o datacenter) o G### (generador)."
            )
        return f"{self._base()}/{route}/{element_id.upper()}"

    # -- session and context -----------------------------------------------------------------

    def start_session(self, point: str | None = None, label: str | None = None) -> dict[str, Any]:
        """Create a new shared session: a private, editable copy of the 188-bus Chilean grid, and make it
        the active one. Call this first. `point` pins one operating point (feb2025-1500, feb2025-0300,
        nov2026-1300 default, nov2026-2000). Returns the session id and a link to watch it in the web map."""
        body = {k: v for k, v in {"point": point, "label": label}.items() if v}
        doc = self.client.post("/sessions", body)
        self.state.session_id, self.state.run_id = doc["session_id"], None
        return {
            "session_id": doc["session_id"],
            "point": doc["point"],
            "share_path": doc["share_path"],
            "expires_at": doc["expires_at"],
            "note": "El id de sesión es una capacidad: quien lo tenga puede editarla. No lo publiques.",
        }

    def join_session(self, session_id: str) -> dict[str, Any]:
        """Make an existing session (shared by someone else, or from the web URL ?sesion=<id>) the active one."""
        doc = self.client.get(f"/sessions/{session_id}")
        self.state.session_id = session_id
        runs = doc.get("runs", {})
        self.state.run_id = next(reversed(runs), None) if runs else None
        return {
            "session_id": session_id,
            "point": doc["point"],
            "runs": list(runs),
            "open_lines": doc["open_lines"],
        }

    def end_session(self) -> dict[str, Any]:
        """Delete the active session and everything in it. Only when the user asks to discard it."""
        sid = self.state.need_session()
        self.client.delete(f"/sessions/{sid}")
        self.state.session_id = self.state.run_id = None
        return {"deleted": True}

    def list_options(self) -> dict[str, Any]:
        """List what can be chosen: operating points, run templates, policies, event types, defensive
        actions with the roles that may propose them, and adversary objectives. Use it to find valid ids."""
        cat = self.client.get("/sim/catalog")
        return {
            "operating_points": cat["operating_points"],
            "templates": [t["id"] for t in cat["templates"]],
            "policies": [p["id"] for p in cat["policies"]],
            "events": [
                {"id": e["id"], "targets": e["targets"], "defaults": e["defaults"]} for e in cat["events"]
            ],
            "actions": [
                {"id": a["id"], "roles": a["proposers"], "target": a["target"]} for a in cat["actions"]
            ],
            "adversary_objectives": cat["objectives"],
            "notice": digest.NOTICE,
        }

    def describe_network(self, focus: str | None = None) -> dict[str, Any]:
        """Describe the session network. Without `focus`: areas A01-A13 with demand, generation and
        population, what the session added, warnings and the baseline (overloaded lines, load shed).
        With `focus` (an area id or name such as A06, or a bus id such as B010): its buses and lines."""
        net = self._network()
        return digest.focus_digest(net, focus) if focus else digest.network_digest(net)

    # -- network edits -----------------------------------------------------------------------

    def add_datacenter(self, bus: str, mw: float, name: str = "Datacenter") -> dict[str, Any]:
        """Add a datacenter (a load) of `mw` megawatts. `bus` is a bus id (B010), an area id or name
        (A02, Antofagasta) or a unique part of a bus name. The rebalance is reported with the
        baseline: `newly_overloaded` are the lines this edit pushed over capacity, while the rest of
        `overloaded_lines` were already over capacity before it."""
        net = self._network()
        bus_id, before = digest.resolve_bus(net, bus), self._overloaded(net)
        resp = self.client.post(
            f"{self._base()}/loads", {"bus": bus_id, "mw": mw, "kind": "datacenter", "name": name}
        )
        return {"bus": bus_id, **digest.edit_digest(resp), **self._after_edit(before)}

    def add_generator(self, bus: str, mw: float, tech: str, name: str | None = None) -> dict[str, Any]:
        """Add a generator of `mw` megawatts at a bus (same bus resolution as add_datacenter). `tech`:
        solar, eolica, hidro, termica, bioenergia, geotermica (the last four are synchronous)."""
        net = self._network()
        bus_id, before = digest.resolve_bus(net, bus), self._overloaded(net)
        body = {
            k: v for k, v in {"bus": bus_id, "mw": mw, "tech": tech, "name": name}.items() if v is not None
        }
        resp = self.client.post(f"{self._base()}/generators", body)
        return {"bus": bus_id, **digest.edit_digest(resp), **self._after_edit(before)}

    def add_line(
        self, a: str, b: str, kv: float, capacity_mw: float, name: str | None = None
    ) -> dict[str, Any]:
        """Add a transmission line between buses `a` and `b` (ids B###) at a base voltage (66, 110, 154,
        220 or 500 kV) and a thermal capacity in MW."""
        body = {
            k: v for k, v in {"a": a, "b": b, "kv": kv, "capacity_mw": capacity_mw, "name": name}.items() if v
        }
        before = self._overloaded()
        resp = self.client.post(f"{self._base()}/lines", body)
        return {**digest.edit_digest(resp), **self._after_edit(before)}

    def add_bus(self, name: str, lat: float, lon: float, kv: float) -> dict[str, Any]:
        """Add a new bus (substation) at a location. It starts isolated: connect it with add_line."""
        before = self._overloaded()
        resp = self.client.post(f"{self._base()}/buses", {"name": name, "lat": lat, "lon": lon, "kv": kv})
        return {**digest.edit_digest(resp), **self._after_edit(before)}

    def edit_element(self, element_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Change an element by id. Bus B###: name, kv, lat, lon, load_mw, gen_mw, sync_mw, inertia_mws,
        in_service. Line R###/U###: capacity_mw, x_pu, in_service. Load or datacenter D###: mw, kind,
        name, in_service. Generator G###: mw, tech, synchronous, inertia_h, name, in_service. Base
        elements are taken out with in_service=false, not deleted."""
        before = self._overloaded()
        resp = self.client.patch(self._element_path(element_id), changes)
        return {"id": element_id.upper(), **digest.edit_digest(resp), **self._after_edit(before)}

    def remove_element(self, element_id: str) -> dict[str, Any]:
        """Delete an element the session added (U###, D###, G###, or a B### nothing uses). Base elements
        answer 409: use edit_element with in_service=false."""
        before = self._overloaded()
        resp = self.client.delete(self._element_path(element_id))
        return {"removed": element_id.upper(), **digest.edit_digest(resp or {}), **self._after_edit(before)}

    def reset_network(self) -> dict[str, Any]:
        """Remove every edit and open line of the session; runs keep the dataset they were created with."""
        before = self._overloaded()
        resp = self.client.post(f"{self._base()}/reset")
        return {"reset": True, "warnings": resp.get("warnings", []), **self._after_edit(before)}

    def _overloaded(self, net: dict[str, Any] | None = None) -> list[str]:
        """Lines over capacity in the base case right now (before an edit)."""
        return (net or self._network()).get("baseline", {}).get("overloaded", [])

    def _after_edit(self, before: list[str]) -> dict[str, Any]:
        """The baseline after an edit and what the edit changed: the base case can already have
        overloaded lines, so only `newly_overloaded` is the edit's doing."""
        base = digest.baseline_digest(self._network().get("baseline", {}))
        now = set(base["overloaded_lines"])
        base["newly_overloaded"] = sorted(now - set(before))
        base["no_longer_overloaded"] = sorted(set(before) - now)
        return {"baseline": base, "notice": digest.NOTICE}

    # -- sandbox -----------------------------------------------------------------------------

    def cut_lines(self, lines: list[str]) -> dict[str, Any]:
        """Open 1 to 3 transmission lines (ids R###/U###) and simulate the cascade: load shed, people
        without power, islands and frequency. It models the effect of losing the lines, never how. The
        lines stay open for everyone in the session until repair_lines."""
        return digest.cut_digest(self.client.post(f"{self._base()}/cut", {"lines": lines}))

    def repair_lines(self, lines: list[str] | None = None) -> dict[str, Any]:
        """Close the given lines again, or every open line when `lines` is omitted."""
        body: dict[str, Any] = {"lines": lines} if lines else {"all": True}
        return digest.cut_digest(self.client.post(f"{self._base()}/repair", body))

    def get_grid_state(self) -> dict[str, Any]:
        """Current sandbox state: open lines and the resulting cascade summary."""
        return digest.cut_digest(self.client.get(f"{self._base()}/state"))

    # -- strategic runs ----------------------------------------------------------------------

    def start_run(
        self,
        template: str = "open_field",
        policy: Literal["A", "B", "C"] = "C",
        seed: int | None = None,
        horizon: int = 24,
        adversary_objective: str | None = None,
        adversary_budget: int = 8,
    ) -> dict[str, Any]:
        """Start a strategic run on the session network and make it the active one. `template` and the
        adversary objectives come from list_options; `policy` A reactive, B preventive, C adaptive
        coordination. Passing `adversary_objective` enables the abstract adversary, which only plays
        events of the catalog against the defender's decision quality."""
        body: dict[str, Any] = {"template": template, "policy": policy, "horizon": horizon}
        if seed is not None:
            body["seed"] = seed
        if adversary_objective:
            body["adversary"] = {
                "enabled": True,
                "objective": adversary_objective,
                "budget": adversary_budget,
                "adaptive": True,
            }
        run = self.client.post(f"{self._base()}/runs", body)
        self.state.run_id = run["run_id"]
        return {**digest.run_digest(run), "notice": digest.NOTICE}

    def inject_event(self, type: str, target: str, share: float | None = None) -> dict[str, Any]:
        """Trigger an event of the abstract catalog at the next cycle (types from list_options, for
        example C3_transmission_opening or D1_telemetry_loss). `target` is an area (A06), zone (NG),
        corridor (A06-A07), bus B###, line R### or defence function. `share` overrides the size."""
        body: dict[str, Any] = {"type": type, "target": target}
        if share is not None:
            body["params"] = {"share": share}
        resp = self.client.post(f"{self._run()}/events", body)
        return {
            "accepted": resp["accepted"],
            "applies_at_cycle": resp["applies_at_cycle"],
            "resolved_target": resp["resolved_target"],
            "notice": digest.NOTICE,
        }

    def step(self, cycles: int = 1) -> dict[str, Any]:
        """Advance the active run 1 to 72 cycles (5 minutes each) and summarise each cycle: served MW,
        consequence level, people without power, alarms and the defensive actions executed."""
        resp = self.client.post(f"{self._run()}/step", {"cycles": cycles})
        return {
            "run": digest.run_digest(resp["run"]),
            "cycles": [digest.snapshot_digest(s) for s in resp["snapshots"]],
            "notice": digest.NOTICE,
        }

    def submit_action(
        self, action: str, target: str, role: Literal["operations", "stabilization", "logistics", "isr"]
    ) -> dict[str, Any]:
        """Queue a defensive action (ids from list_options) for the next cycle, as `role`, one of the
        action's proposers. It goes through the validator and resources; it is not capped by C2's choice."""
        resp = self.client.post(f"{self._run()}/actions", {"action": action, "target": target, "role": role})
        return {
            "accepted": resp["accepted"],
            "applies_at_cycle": resp["applies_at_cycle"],
            "notice": resp.get("notice", digest.NOTICE),
        }

    def run_status(self) -> dict[str, Any]:
        """Where the active run stands: cycle, latest snapshot summary and remaining resources."""
        resp = self.client.get(self._run())
        latest = resp.get("latest")
        return {
            "run": digest.run_digest(resp["run"]),
            "latest": digest.snapshot_digest(latest) if latest else None,
            "resources": resp.get("resources"),
            "notice": digest.NOTICE,
        }

    def run_report(self) -> dict[str, Any]:
        """Indicators of the active run: mission continuity, response capacity, consequence level
        (L0-L3), people without power, unserved energy and cost. Values are modelled, see is_assumption."""
        return digest.report_digest(self.client.get(f"{self._run()}/report"))

    def after_action(self) -> dict[str, Any]:
        """The after-action review of the active run in Spanish: summary, key moments and lessons."""
        resp = self.client.get(f"{self._run()}/after_action")
        return {k: resp.get(k) for k in ("summary", "moments", "narrative", "policy", "notice")}

    def replay(self, policy: Literal["A", "B", "C"] | None = None) -> dict[str, Any]:
        """Re-run the active run with the same seed and events under another policy, to compare policies.
        The new run becomes the active one."""
        body = {"policy": policy} if policy else {}
        resp = self.client.post(f"{self._run()}/replay", body)
        self.state.run_id = resp["run_id"]
        return {**digest.run_digest(resp), "replay_of": resp.get("replay_of"), "notice": digest.NOTICE}
