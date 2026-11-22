"""Simulate a grid with several edits at once, without a session (docs/grids.md).

Why: the browser keeps the list of changes the user made (lines cut, substations out of service) and asks the
backend what the cascade looks like with all of them applied together. The cache only has single cuts, so this is
the path for two or more changes. Nothing is stored: the same request gives the same timeline.
"""

from __future__ import annotations

from cascadasen.application.grids import GridError
from cascadasen.domain.cascade.engine import run_cascade_workflow
from cascadasen.domain.cascade.overlay import OverlayError, apply_overlay, empty_overlay
from cascadasen.domain.theater.world import TheaterWorld

MAX_EDITS = 50  # lines plus substations in one request


class GridSimulator:
    def __init__(self, world: TheaterWorld) -> None:
        self.world = world

    def simulate_workflow(self, point: str, open_lines: list[str], out_buses: list[str]) -> dict:
        _check_size(open_lines, out_buses)
        net, op = self._load(point)
        _check_known(net.buses, open_lines, out_buses)
        edited = _apply(net.buses, op, out_buses)
        live = {ln.id for ln in edited.net.lines}
        kept = sorted(set(open_lines) & live)
        timeline = run_cascade_workflow(edited.net, edited.point, kept)
        direct = _direct_loss(op, out_buses)
        return {
            "point": point,
            "open_lines": kept,
            "out_buses": sorted(set(out_buses)),
            # lines that went with their substation: they are out already, not cut twice
            "dropped_lines": sorted(set(open_lines) - live),
            "direct": direct,
            "warnings": edited.warnings,
            "timeline": _mark_out_of_service(timeline, out_buses, direct),
        }

    def _load(self, point: str):
        try:
            return self.world.load(point)
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
    """A substation out of service is dark in every frame and its people and load add to the summary.

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
    return timeline
