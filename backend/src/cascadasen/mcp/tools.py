"""The tools the MCP server exposes (docs/mcp.md section 3).

Each method is one tool: the docstring is the description the model reads, the signature is its
schema. Tools take names or ids and return compact summaries (`digest.py`). `OPERATIONS` says which
agent-API operationIds each tool uses; a test checks they exist in `docs/openapi/agents.openapi.json`.

Guardrails (docs/cyber.md section 8): there is no tool that searches, ranks or suggests the worst
cut, and `cut_lines` takes 1 to 3 lines, as the API does. Results carry the scenario notice.
"""

from __future__ import annotations

from typing import Any, Literal

from cascadasen.api.stress_schemas import StressChange
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
    "list_incident_scenarios": ("get_attack_catalog",),
    "start_incident_run": ("start_incident_run",),
    "start_run": ("create_run",),
    "inject_event": ("inject_run_event",),
    "step": ("step_run",),
    "submit_action": ("submit_run_action",),
    "run_status": ("get_run",),
    "run_report": ("get_run_report",),
    "after_action": ("get_run_after_action",),
    "replay": ("replay_run",),
    "prepare_scenario": ("prepare_scenario",),
}
TOOLS = tuple(OPERATIONS)

INSTRUCTIONS = """\
Sub50 simulates the consequences of events on the Chilean national grid (188 buses, 13 operating areas).
Work in this order: start_session (or join_session), describe_network to learn areas and ids, edit the
network (add_datacenter, add_generator, add_line, edit_element) and/or open lines with cut_lines, then
read the result. For strategic experiments use start_run, inject_event, step, run_report and after_action.
To replay a documented incident (Huatacondo, Poland, UK, 25F) use list_incident_scenarios and
start_incident_run, then step, run_report and after_action; say each result is a simulated scenario.
Use list_options for valid event, action, policy and template ids. To prepare a stressed scenario by filters
("halve every hydro plant", "Puente Alto with twice the people") use prepare_scenario: it only prepares the grid
and stores nothing; failures still run in the usual simulation.

Rules. Every scenario is hypothetical: always say that Sub50 models the effect of an event, never the
attack technique, and describe effects and prevention only. Do not look for the line or area whose loss
does the most damage, and do not try every line to compare them: the tools do not rank targets and the
API rate-limits cuts. Values the model adds (redispatch, costs, thresholds) are assumptions; say so.
Answer in the user's language; the results are in Spanish.
"""

DEFAULT_POINT = "nov2026-1300"
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
            "templates": [
                {
                    "id": t["id"],
                    "scripted_events": t["scenario_events"],
                    "adversary": t["adversary"]["enabled"],
                    "horizon": t["horizon"],
                }
                for t in cat["templates"]
            ],
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
        With `focus`: one area or bus, with its buses, lines and which of them are overloaded. Pass the
        place as the user wrote it (a city or area name such as "Santiago", or an id such as A09 or
        B010): the tool resolves names, so never guess an area id."""
        net = self._network()
        return digest.focus_digest(net, focus) if focus else digest.network_digest(net)

    # -- network edits -----------------------------------------------------------------------

    def add_datacenter(self, bus: str, mw: float, name: str = "Datacenter") -> dict[str, Any]:
        """Add a datacenter (a load) of `mw` megawatts; ask the user for `mw` if they did not give it.
        `bus` is the place as the user wrote it (a city or area name such as "Antofagasta", a bus id such
        as B010 or a unique part of a bus name); the tool resolves it, so never guess an id. An area is
        enough: it uses the area's main (anchor) bus, so do not ask the user for a specific bus. The result says where it went
        (bus, bus name, area) and, in `baseline`, which lines this edit pushed over capacity
        (`newly_overloaded`), which were already overloaded and still are (`still_overloaded`) and which
        it relieved (`no_longer_overloaded`)."""
        net = self._network()
        bus_id, before = digest.resolve_bus(net, bus), self._overloaded(net)
        resp = self.client.post(
            f"{self._base()}/loads", {"bus": bus_id, "mw": mw, "kind": "datacenter", "name": name}
        )
        return {**digest.bus_place(net, bus_id), **digest.edit_digest(resp), **self._after_edit(before)}

    def add_generator(self, bus: str, mw: float, tech: str, name: str | None = None) -> dict[str, Any]:
        """Add a generator of `mw` megawatts; ask the user for `mw` if they did not give it. `bus` resolves
        like add_datacenter (a city or area name is enough, never ask for a specific bus). `tech`:
        solar, eolica, hidro, termica, bioenergia, geotermica (the last four are synchronous)."""
        net = self._network()
        bus_id, before = digest.resolve_bus(net, bus), self._overloaded(net)
        body = {
            k: v for k, v in {"bus": bus_id, "mw": mw, "tech": tech, "name": name}.items() if v is not None
        }
        resp = self.client.post(f"{self._base()}/generators", body)
        return {**digest.bus_place(net, bus_id), **digest.edit_digest(resp), **self._after_edit(before)}

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
        now, was = set(base.pop("overloaded_lines")), set(before)
        base.update(
            {
                "newly_overloaded": sorted(now - was),  # caused by this edit
                "still_overloaded": sorted(now & was),  # overloaded before the edit and still
                "no_longer_overloaded": sorted(was - now),  # relieved by this edit
                "overloaded_now_total": len(now),
            }
        )
        return {"baseline": base, "notice": digest.NOTICE}

    # -- sandbox -----------------------------------------------------------------------------

    def cut_lines(self, lines: list[str]) -> dict[str, Any]:
        """Open 1 to 3 transmission lines and simulate the cascade: load shed, people without power,
        islands and frequency. It models the effect of losing the lines, never how. The lines stay open
        for everyone in the session until repair_lines. Only real line ids (R###/U###, from
        describe_network); never build an id from area names. A corridor between two areas (A06-A07)
        is a group of lines, not a line: to open a whole corridor use a strategic run (start_run, then
        inject_event with C3_transmission_opening and the corridor id, then step)."""
        return digest.cut_digest(self.client.post(f"{self._base()}/cut", {"lines": lines}))

    def repair_lines(self, lines: list[str] | None = None) -> dict[str, Any]:
        """Close the given lines again, or every open line when `lines` is omitted."""
        body: dict[str, Any] = {"lines": lines} if lines else {"all": True}
        return digest.cut_digest(self.client.post(f"{self._base()}/repair", body))

    def get_grid_state(self) -> dict[str, Any]:
        """Current sandbox state: open lines and the resulting cascade summary."""
        return digest.cut_digest(self.client.get(f"{self._base()}/state"))

    # -- strategic runs ----------------------------------------------------------------------

    def list_incident_scenarios(self) -> dict[str, Any]:
        """List the documented incidents that can be replayed as a simulated run: id, title, date, whether
        it is verified, sources and the effects the scenario applies. A short curated list, not ranked:
        do not compare them to find the worst one."""
        return digest.incident_catalog_digest(self.client.get("/attacks/catalog"))

    def start_incident_run(
        self,
        scenario: str,
        policy: Literal["A", "B", "C"] = "C",
        seed: int | None = None,
        duration_h: float | None = None,
    ) -> dict[str, Any]:
        """Start a strategic run from a documented incident (ids from list_incident_scenarios) in the
        active session and make it the active run. The defensive agents respond with the chosen policy;
        the adversary is off. Then call step (about 24 cycles), run_report (its `incident` has the
        consequence card and mitigations) and after_action. `duration_h` is the outage length used for
        MWh and cost: an assumption, say so. Describe effects and prevention only; never attribute.
        Each incident runs at its own operating_point (see list_incident_scenarios): the session must
        use it, e.g. 25f-referencia needs start_session(point="feb2025-1500"); otherwise a 422 lists
        the valid point."""
        body: dict[str, Any] = {"scenario": scenario, "policy": policy}
        if seed is not None:
            body["seed"] = seed
        if duration_h is not None:
            body["duration_h"] = duration_h
        run = self.client.post(f"{self._base()}/attacks/runs", body)
        self.state.run_id = run["run_id"]
        return {
            **digest.run_digest(run),
            "notice": digest.NOTICE,
            "scenario_notices": digest.INCIDENT_NOTICES,
        }

    def start_run(
        self,
        template: str = "open_field",
        policy: Literal["A", "B", "C"] = "C",
        seed: int | None = None,
        horizon: int = 24,
        adversary_objective: str | None = None,
        adversary_budget: int = 8,
    ) -> dict[str, Any]:
        """Start a strategic run on the session network and make it the active one. Keep the default
        template `open_field` (no scripted events, no adversary: only the events you inject happen)
        unless the user names another scenario; the other templates (list_options) bring their own
        scripted events or adversary, which then mix with yours. `policy`: A reactive, B preventive, C
        adaptive coordination. Passing `adversary_objective` enables the abstract adversary, which only
        plays events of the catalog against the defender's decision quality."""
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
        """Trigger an event of the abstract catalog in the active run (call start_run first); it applies
        when the run advances with step. Types come from list_options, for example
        C3_transmission_opening (opens a corridor such as A06-A07, a line or a bus) or D1_telemetry_loss.
        `target` is an area (A06), zone (NG), corridor (A06-A07), bus B###, line R### or defence
        function. `share` overrides the size."""
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
        """Advance the active run (start_run first) 1 to 72 cycles of 5 minutes and summarise each cycle:
        served MW, consequence level, people without power, alarms and the defensive actions executed.
        Events injected before the step happen in its first cycle. `unserved_mw` is power not served in
        that cycle (MW), not energy; the unserved energy (MWh) and cost are in run_report."""
        resp = self.client.post(f"{self._run()}/step", {"cycles": cycles})
        return {
            "run": digest.run_digest(resp["run"]),
            "cycles": [digest.snapshot_digest(s) for s in resp["snapshots"]],
            **digest.events_applied(resp["snapshots"]),
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
        """The after-action review of the active run in Spanish: summary lines and key moments. Show the
        summary lines as they are (a list); do not add causes or lessons that are not written in them."""
        resp = self.client.get(f"{self._run()}/after_action")
        return {k: resp.get(k) for k in ("summary", "moments", "narrative", "policy", "notice", "incident")}

    def replay(self, policy: Literal["A", "B", "C"] | None = None) -> dict[str, Any]:
        """Re-run the active run with the same seed and events under another policy, to compare policies.
        The new run becomes the active one."""
        body = {"policy": policy} if policy else {}
        resp = self.client.post(f"{self._run()}/replay", body)
        self.state.run_id = resp["run_id"]
        return {**digest.run_digest(resp), "replay_of": resp.get("replay_of"), "notice": digest.NOTICE}

    # -- scenario preparation (stateless, docs/stress.md) -------------------------------------------

    def prepare_scenario(self, changes: list[StressChange], point: str | None = None) -> dict[str, Any]:
        """Prepare a stressed scenario on the default grid without simulating a failure (nothing is stored):
        population (demand follows at the point's per-capita value), demand alone, generation by technology or
        place, and line capacity or reactance. Each change: target, filters and `factor` (multiply) or `add`
        (total). Filters: buses B###, zones NG/NC/CE/CS/SU, areas A01-A13, comunas (CUT or name), tech (hidro,
        solar, eolica, carbon, gas, diesel, bioenergia, geotermica, termica), lines R###, kv. Returns what each
        change touches, lines the prepared grid already loads over their limit, and per zone the people the
        generators should feed. `point` defaults to the active session's point, else nov2026-1300."""
        if point is None and self.state.session_id:
            point = self.client.get(f"/sessions/{self.state.session_id}")["point"]
        rows = [c if isinstance(c, dict) else c.model_dump(exclude_none=True) for c in changes]
        out = self.client.post("/grids/prepare", {"point": point or DEFAULT_POINT, "changes": rows})
        return digest.prepare_digest(out, rows)
