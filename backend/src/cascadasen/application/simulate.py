"""Use case: one physical contingency on the reduced network -> timeline.json (docs/stack.md 7)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.simulation.consequence import consequence_card
from cascadasen.domain.simulation.defenses import DefenseSet, defense_sets, documented_trips_25f
from cascadasen.domain.simulation.engine import Change, run_transient
from cascadasen.domain.simulation.grid import GridState, Physics, build_state, operating_points
from cascadasen.domain.simulation.network import ReducedNetwork, Resolved, UnknownTargetError
from cascadasen.domain.simulation.timeline import build_timeline

BEHAVIORS = ("per_code", "as_happened")
MAX_BATTERY_MW = 5000.0
MAX_OUTAGE_H = 2160.0
TIMEOUT_S = 2.0


class SimulationInputError(ValueError):
    """Invalid input; maps to HTTP 422 with the valid values when there is a closed set."""

    def __init__(self, field: str, message: str, valid: list[str] | None = None) -> None:
        super().__init__(message)
        self.field, self.message, self.valid = field, message, valid or []

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {"field": self.field, "message": self.message}
        if self.valid:
            out["valid"] = self.valid
        return out


class SimulationTimeoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class SimulateCommand:
    scenario: str
    defenses: str
    behavior: str = "per_code"
    elements_out: list[str] = field(default_factory=list)
    battery_mw: dict[str, float] = field(default_factory=dict)
    group_out: list[dict[str, Any]] = field(default_factory=list)
    defenses_disabled: list[str] = field(default_factory=list)
    outage_duration_h: float | None = None
    cause: str = "failure"
    frames: bool = True


def element_changes(network: ReducedNetwork, element: str) -> tuple[list[Change], Resolved]:
    """Translate a selected element into the physical changes of a transmission opening (C3)."""
    r = network.resolve(element)
    if r.kind == "corridor":
        return [Change("open_corridor", r.id)], r
    if r.kind == "node":
        return [Change("node_out", r.id)], r
    if r.kind == "area":
        main = network.areas[r.id].main_node
        if main is None:
            raise UnknownTargetError(element)
        return [Change("node_out", main)], r
    if r.corridor:
        return [Change("lines_out", r.corridor, lines=(r.id,))], r
    raise SimulationInputError(
        "elements_out", f"{element}: línea interna de un área, el modelo reducido no la representa"
    )


def apply_batteries(network: ReducedNetwork, state: GridState, battery_mw: dict[str, float]) -> None:
    for key, mw in battery_mw.items():
        if key in network.areas:
            state.battery_mw[key] = state.battery_mw.get(key, 0.0) + mw
            continue
        areas = network.zone_areas(key)
        load = sum(state.load_mw[a] for a in areas)
        for a in areas:
            state.battery_mw[a] = state.battery_mw.get(a, 0.0) + (
                mw * state.load_mw[a] / load if load else 0.0
            )


class PhysicsSimulator:
    def __init__(self, network: ReducedNetwork, physics: Physics | None = None) -> None:
        self.network = network
        self.physics = physics or Physics.load()

    def _validate(self, cmd: SimulateCommand) -> None:
        net = self.network
        if cmd.scenario not in operating_points():
            raise SimulationInputError("scenario", "escenario desconocido", sorted(operating_points()))
        if cmd.defenses not in defense_sets():
            raise SimulationInputError("defenses", "conjunto de defensas desconocido", sorted(defense_sets()))
        if cmd.behavior not in BEHAVIORS:
            raise SimulationInputError("behavior", "comportamiento desconocido", list(BEHAVIORS))
        if cmd.behavior == "as_happened" and cmd.scenario != "25F":
            raise SimulationInputError(
                "behavior", "'as_happened' solo es válido con el escenario 25F", ["per_code"]
            )
        if len(cmd.elements_out) != len(set(cmd.elements_out)) or len(cmd.elements_out) > 3:
            raise SimulationInputError("elements_out", "de 1 a 3 ids distintos")
        if not cmd.elements_out and not cmd.group_out and not cmd.defenses_disabled:
            raise SimulationInputError("elements_out", "indica al menos un elemento, un grupo o una defensa")
        targets = set(net.areas) | set(net.zones)
        for k, mw in cmd.battery_mw.items():
            if k not in targets:
                raise SimulationInputError("battery_mw", f"{k}: área o zona desconocida", sorted(targets))
            if not 0 <= mw <= MAX_BATTERY_MW:
                raise SimulationInputError("battery_mw", f"{k}: entre 0 y {MAX_BATTERY_MW:.0f} MW")
        techs = sorted({t for a in net.areas.values() for t in a.installed_mw})
        for g in cmd.group_out:
            if g.get("zone") not in net.zones:
                raise SimulationInputError("group_out", "zona desconocida", net.zones)
            if g.get("tech") not in techs:
                raise SimulationInputError("group_out", "tecnología desconocida", techs)
            if not 0 <= float(g.get("share", -1)) <= 1:
                raise SimulationInputError("group_out", "share entre 0 y 1")
        valid_def = DefenseSet.load(cmd.defenses).defense_ids(net.zones)
        for d in cmd.defenses_disabled:
            if d not in valid_def:
                raise SimulationInputError("defenses_disabled", f"{d}: defensa desconocida", valid_def)
        if cmd.outage_duration_h is not None and not 0 <= cmd.outage_duration_h <= MAX_OUTAGE_H:
            raise SimulationInputError("outage_duration_h", f"entre 0 y {MAX_OUTAGE_H:.0f} horas")

    def simulate(self, cmd: SimulateCommand) -> dict[str, Any]:
        self._validate(cmd)
        started = time.perf_counter()
        net, physics = self.network, self.physics
        defenses = DefenseSet.load(cmd.defenses)
        state = build_state(net, cmd.scenario, physics)
        apply_batteries(net, state, cmd.battery_mw)
        changes: list[Change] = [Change("disable_defense", d) for d in cmd.defenses_disabled]
        resolved = []
        for el in cmd.elements_out:
            try:
                chs, r = element_changes(net, el)
            except UnknownTargetError as exc:
                raise SimulationInputError("elements_out", f"{el}: elemento desconocido") from exc
            changes += chs
            resolved.append(
                {
                    "input": el,
                    "kind": r.kind,
                    "id": r.id,
                    "area": r.area,
                    "corridor": r.corridor,
                    "note": r.note,
                }
            )
        changes += [
            Change("group_out", g["zone"], share=float(g["share"]), tech=g["tech"]) for g in cmd.group_out
        ]
        res = run_transient(
            net,
            state,
            changes,
            defenses,
            physics,
            behavior=cmd.behavior,
            scenario=cmd.scenario,
            full=cmd.frames,
        )
        outage = cmd.outage_duration_h if cmd.outage_duration_h is not None else physics.default_outage_h
        card = consequence_card(
            res.islands,
            res.load_lost_mw,
            res.load_shed_mw,
            res.people_without_power,
            outage,
            cmd.outage_duration_h is None,
            physics.voll_usd_per_kwh,
        )
        provenance = [*net.provenance, *physics.provenance, *state.provenance, *defenses.provenance]
        if cmd.behavior == "as_happened":
            provenance += documented_trips_25f()[1]
        cause = None
        if cmd.cause == "cyber_effect":
            cause = {
                "kind": "cyber_effect",
                "scenario_class": "C3" if cmd.elements_out else "C2",
                "label_key": "cyber_hypothetical",
                "references": ["[34]"],
            }
        timeline = build_timeline(
            net,
            res,
            card,
            physics,
            scenario=cmd.scenario,
            defenses=cmd.defenses,
            behavior=cmd.behavior,
            failed_elements=list(cmd.elements_out),
            provenance=provenance,
            cause=cause,
            group_out=cmd.group_out or None,
            defenses_disabled=cmd.defenses_disabled or None,
            frames=cmd.frames,
        )
        timeline["elements_resolved"] = resolved
        if time.perf_counter() - started > TIMEOUT_S:
            raise SimulationTimeoutError("timeout")
        return timeline
