"""Simulate a grid with several edits at once, without a session (docs/grids.md).

Why: the browser keeps the list of changes the user made (lines cut, substations out of service) and asks the
backend what the cascade looks like with all of them applied together. The cache only has single cuts, so this is
the path for two or more changes. Nothing is stored: the same request gives the same timeline.
"""

from __future__ import annotations

from cascadasen.application.grids import GridError
from cascadasen.domain.cascade.engine import failure_cost, run_cascade_workflow
from cascadasen.domain.cascade.frequency import cascade_params
from cascadasen.domain.cascade.health import with_event_health
from cascadasen.domain.cascade.overlay import OverlayError, apply_overlay, empty_overlay
from cascadasen.domain.simulation.params import load_params, value
from cascadasen.domain.theater.world import TheaterWorld

MAX_EDITS = 50  # lines plus substations in one request


class GridSimulator:
    def __init__(self, world: TheaterWorld) -> None:
        self.world = world

    def simulate_workflow(self, point: str, open_lines: list[str], out_buses: list[str]) -> dict:
        op, edited, kept, dropped = prepare_edits(self.world, point, open_lines, out_buses)
        timeline = run_cascade_workflow(edited.net, edited.point, kept)
        direct = _direct_loss(op, out_buses)
        return {
            "point": point,
            "open_lines": kept,
            "out_buses": sorted(set(out_buses)),
            "dropped_lines": dropped,  # lines that went with their substation: they are out already, not cut twice
            "direct": direct,
            "warnings": edited.warnings,
            "timeline": with_event_health(_mark_out_of_service(timeline, out_buses, direct)),
        }


def cost_workflow(simulator: GridSimulator, point: str, open_lines: list[str], out_buses: list[str]) -> dict:
    """Failure cost of the user's changes, total and per hour of outage (docs/engine.md, "Cost"). No change: no cost."""
    if not (open_lines or out_buses):
        _load(simulator.world, point)  # still 404 for an unknown point
        return _cost_view(point, failure_cost(0.0, 0.0, 0.0), 0.0)
    summary = simulator.simulate_workflow(point, open_lines, out_buses)["timeline"]["summary"]
    return _cost_view(point, {k: summary[k] for k in COST_KEYS}, summary["people_without_power"])


COST_KEYS = (
    "failure_cost_usd",
    "cost_per_hour_usd",
    "unserved_energy_mwh",
    "outage_duration_h",
    "cost_breakdown",
)


def _cost_view(point: str, cost: dict, people: float) -> dict:
    params = cascade_params()["cost"]
    voll = load_params("physics")["voll_usd_per_kwh"]
    return {
        "point": point,
        "cost_usd": cost["failure_cost_usd"],
        "cost_per_hour_usd": cost["cost_per_hour_usd"],
        "energy_not_served_mwh": cost["unserved_energy_mwh"],
        "outage_hours": {
            **cost["outage_duration_h"],
            "note": "black start" if cost["cost_breakdown"]["dark_mw"] > 0 else "EDAC",
        },
        "unserved_cost_usd_per_mwh": {
            "value": round(float(value(voll)) * 1000.0),
            "source": voll.get("source"),
        },
        "breakdown": cost["cost_breakdown"],
        "people_without_power": people,
        "assumptions": [str(params[k].get("note") or params[k].get("source")).strip() for k in params],
    }


def prepare_edits(
    world: TheaterWorld, point: str, open_lines: list[str], out_buses: list[str], allow_empty: bool = False
):
    """The base point, the network with the substations out of service, the lines to open on it and the lines that went
    with their substation. Shared by every use case that works on the user's changes (simulate, dependency)."""
    if not allow_empty:
        _check_size(open_lines, out_buses)
    elif len(set(open_lines)) + len(set(out_buses)) > MAX_EDITS:
        raise GridError("invalid", f"Máximo {MAX_EDITS} cambios por simulación")
    net, op = _load(world, point)
    _check_known(net.buses, open_lines, out_buses)
    edited = _apply(net.buses, op, out_buses)
    live = {ln.id for ln in edited.net.lines}
    return op, edited, sorted(set(open_lines) & live), sorted(set(open_lines) - live)


def _load(world: TheaterWorld, point: str):
    try:
        return world.load(point)
    except KeyError as exc:
        raise GridError("not_found", f"No existe el punto de operación: {point}") from exc


def _check_size(open_lines: list[str], out_buses: list[str]) -> None:
    if not (open_lines or out_buses):
        raise GridError("invalid", "Indica al menos una línea o una subestación")
    if len(set(open_lines)) + len(set(out_buses)) > MAX_EDITS:
        raise GridError("invalid", f"Máximo {MAX_EDITS} cambios por simulación")


def _check_known(net, open_lines: list[str], out_buses: list[str]) -> None:
    lines = {ln.id for ln in net.lines}
    buses = {f"B{i:03d}" for i in range(net.size)}
    for kind, wanted, known in (("líneas", open_lines, lines), ("subestaciones", out_buses, buses)):
        unknown = sorted(set(wanted) - known)
        if unknown:
            raise GridError("not_found", f"No existen estas {kind} en este punto: {', '.join(unknown)}")


def _apply(net, op, out_buses: list[str]):
    overlay = empty_overlay()
    overlay["bus_overrides"] = {b: {"in_service": False} for b in set(out_buses)}
    try:
        return apply_overlay(net, op, overlay)
    except OverlayError as exc:
        raise GridError("invalid", exc.message) from exc


def _direct_loss(op, out_buses: list[str]) -> dict:
    """What the outage itself takes away, before any cascade: the engine rebalances it but does not count it."""
    idx = [int(b[1:]) for b in set(out_buses)]
    return {
        "load_mw": round(float(sum(op.load[i] for i in idx)), 1),
        "gen_mw": round(float(sum(op.gen[i] for i in idx)), 1),
        "people": round(float(sum(op.people[i] for i in idx))),
    }


def _mark_out_of_service(timeline: dict, out_buses: list[str], direct: dict) -> dict:
    """A substation out of service is dark in every frame and its people, load and failure cost add to the summary.

    ASSUMPTION: the engine drops the out bus before the cascade, so the cascade never counts it; adding it here
    does not count it twice.
    """
    if out_buses:
        for frame in timeline["frames"]:
            frame["dark"] = sorted(set(frame["dark"]) | set(out_buses))
        summary = timeline["summary"]
        summary["people_without_power"] += direct["people"]
        summary["load_shed_mw"] = round(summary["load_shed_mw"] + direct["load_mw"], 1)
        summary["load_total_mw"] = round(
            summary["load_total_mw"] + direct["load_mw"], 1
        )  # the demand of the hour
        summary["dark_buses"] += len(set(out_buses))
        summary["dark_load_mw"] = round(summary.get("dark_load_mw", 0.0) + direct["load_mw"], 1)
        # the cost follows the MW lost, direct loss included: a substation out of service is dark demand
        summary.update(
            failure_cost(summary["load_shed_mw"], summary["dark_load_mw"], summary["load_total_mw"])
        )
    return timeline
