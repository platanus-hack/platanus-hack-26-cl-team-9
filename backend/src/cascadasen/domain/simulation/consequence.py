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


def level_of(n_counted: int, n_collapsed: int, load_lost_mw: float) -> str:
    """The L0-L3 ladder from the islands with load (`n_counted`), how many of them collapse and the MW lost."""
    if n_counted and n_collapsed == n_counted:
        return "L3"
    if n_collapsed:
        return "L2"
    return "L1" if load_lost_mw > 0.5 else "L0"


def consequence_level(islands: list[IslandResult], load_lost_mw: float) -> tuple[str, bool]:
    counted = [i for i in islands if i.result != "no_load"]
    collapsed = [i for i in counted if i.result == "blackout" or i.documented_collapse]
    return level_of(len(counted), len(collapsed), load_lost_mw), any(i.uncertain for i in islands)


def outage_cost(
    load_lost_mw: float, outage_h: float, outage_is_assumption: bool, voll_usd_per_kwh: float
) -> dict[str, Any]:
    """Unserved energy and its regulatory valuation (CNE failure cost [19], stack.md 6.1).

    A valuation for planning, not a measured economic loss. Shared by the consequence card and the
    cascade timeline summary so the formula lives in one place."""
    mwh = load_lost_mw * outage_h
    return {
        "unserved_energy_mwh": round(mwh, 1),
        "failure_cost_usd": round(mwh * 1000.0 * voll_usd_per_kwh),
        "outage_duration_h": {"value": outage_h, "is_assumption": outage_is_assumption},
    }


def blackout_cost(
    dark_mw: float,
    shed_mw: float,
    total_mw: float,
    voll_usd_per_kwh: float,
    blackout_h: float,
    shed_h: float,
    total_multiplier: float,
) -> dict[str, Any]:
    """Failure cost that tells a total blackout from a slow grid (docs/engine.md, "Cost").

        cost = VoLL x [ dark_MW x H_blackout x (1 + (k - 1) x dark_share) + shed_MW x H_shed ]

    `dark_mw`: demand of the buses that went dark (islands that collapsed, substations out): they need a black start,
    H_blackout hours at full outage. `shed_mw`: load cut by EDAC in islands that survive: back in H_shed. `k` adds the
    cost of a total blackout beyond the unserved energy and grows with the share of the demand that went dark."""
    share = min(1.0, dark_mw / total_mw) if total_mw > 0 else 0.0
    factor = 1.0 + (total_multiplier - 1.0) * share
    dark_mwh, shed_mwh = dark_mw * blackout_h, shed_mw * shed_h
    usd_per_mwh = voll_usd_per_kwh * 1000.0
    return {
        "unserved_energy_mwh": round(dark_mwh + shed_mwh, 1),
        "failure_cost_usd": round(usd_per_mwh * (dark_mwh * factor + shed_mwh)),
        # what one hour of this outage costs while it lasts (dark and shed load both still out)
        "cost_per_hour_usd": round(usd_per_mwh * (dark_mw * factor + shed_mw)),
        "outage_duration_h": {"value": blackout_h if dark_mw > 0 else shed_h, "is_assumption": dark_mw <= 0},
        "cost_breakdown": {
            "dark_mw": round(dark_mw, 1),
            "shed_mw": round(shed_mw, 1),
            "dark_share": round(share, 4),
            "total_blackout_factor": round(factor, 4),
        },
    }


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
    return {
        "consequence_level": level,
        "uncertain": uncertain,
        "people_without_power": round(people),
        "load_shed_mw": round(load_shed_mw, 1),
        "load_lost_mw": round(load_lost_mw, 1),
        **outage_cost(load_lost_mw, outage_h, outage_is_assumption, voll_usd_per_kwh),
        "islands": [i.summary() for i in islands],
    }
