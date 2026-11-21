"""Consequence card: level L0-L3, people without power, unserved energy and cost (cyber.md 5, stack.md 6.1).

    L0 absorbed            no island collapses and no load is lost
    L1 contained           load is shed or lost locally; every island survives
    L2 regional blackout   at least one island collapses, not all
    L3 national blackout   every island collapses

A small island without synchronous generation is a "local cut", not a cascade blackout
(stack.md 4.5). Any island outside the model's validity range adds the "uncertain" badge.
"""

from __future__ import annotations

from typing import Any

from cascadasen.domain.simulation.engine import IslandResult


def consequence_level(islands: list[IslandResult], load_lost_mw: float) -> tuple[str, bool]:
    counted = [i for i in islands if i.result != "no_load"]
    collapsed = [i for i in counted if i.result == "blackout" or i.documented_collapse]
    uncertain = any(i.uncertain for i in islands)
    if counted and len(collapsed) == len(counted):
        return "L3", uncertain
    if collapsed:
        return "L2", uncertain
    if load_lost_mw > 0.5:
        return "L1", uncertain
    return "L0", uncertain


def consequence_card(
    islands: list[IslandResult],
    load_lost_mw: float,
    load_shed_mw: float,
    people: float,
    outage_h: float,
    outage_is_assumption: bool,
    voll_usd_per_kwh: float,
) -> dict[str, Any]:
    level, uncertain = consequence_level(islands, load_lost_mw)
    mwh = load_lost_mw * outage_h
    return {
        "consequence_level": level,
        "uncertain": uncertain,
        "people_without_power": round(people),
        "load_shed_mw": round(load_shed_mw, 1),
        "load_lost_mw": round(load_lost_mw, 1),
        "unserved_energy_mwh": round(mwh, 1),
        "failure_cost_usd": round(mwh * 1000.0 * voll_usd_per_kwh),
        "outage_duration_h": {"value": outage_h, "is_assumption": outage_is_assumption},
        "islands": [i.summary() for i in islands],
    }
