"""Compact summaries of API responses for the model (docs/mcp.md section 4).

The raw responses are large (188 buses, frames, per-area snapshots). A tool returns only what answers
the question, always with the scenario `notice`, and keeps `is_assumption` on modelled values.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from cascadasen.mcp.client import ToolError

NOTICE = "Escenario hipotético: se modela el efecto, no el ataque."


def fold(text: str) -> str:
    """Lowercase without accents, for matching names the user typed."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def baseline_digest(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_loading": baseline.get("max_loading"),
        "overloaded_lines": baseline.get("overloaded", []),
        "load_shed_mw": baseline.get("load_shed_mw"),
        "islands": len(baseline.get("islands", [])),
    }


def edit_digest(resp: dict[str, Any]) -> dict[str, Any]:
    """Result of an edit: new id, warnings and the redispatch rule, without the per-bus split."""
    out: dict[str, Any] = {"id": resp.get("id"), "warnings": resp.get("warnings", [])}
    out["redispatch"] = [
        {
            "redispatch_mw": b.get("redispatch_mw"),
            "rule": b.get("rule"),
            "is_assumption": b.get("is_assumption"),
        }
        for b in resp.get("balance", [])
    ]
    return out


def island_digest(island: dict[str, Any]) -> dict[str, Any]:
    keys = ("result", "buses", "min_hz", "final_hz", "rocof_hz_s", "shed_mw")
    return {k: island[k] for k in keys if k in island}


def cut_digest(resp: dict[str, Any]) -> dict[str, Any]:
    summary = (resp.get("timeline") or {}).get("summary") or {}
    return {
        "open_lines": resp.get("open_lines", []),
        "load_shed_mw": summary.get("load_shed_mw"),
        "load_total_mw": summary.get("load_total_mw"),
        "people_without_power": summary.get("people_without_power"),
        "dark_buses": summary.get("dark_buses"),
        "uncertain": summary.get("uncertain"),
        "islands": [island_digest(i) for i in summary.get("islands", [])],
        "notice": resp.get("notice", NOTICE),
    }


def network_digest(net: dict[str, Any]) -> dict[str, Any]:
    """Whole-network overview: areas with demand and generation, what the session added, baseline."""
    buses = net.get("buses", {})
    areas = []
    for a in net.get("areas", []):
        members = [buses[b] for b in a.get("buses", []) if b in buses]
        areas.append(
            {
                "id": a["id"],
                "name": a.get("name"),
                "zone": a.get("zone"),
                "population": a.get("population"),
                "buses": len(a.get("buses", [])),
                "anchor_bus": a.get("anchor_bus"),
                "load_mw": round(sum(m.get("load_mw", 0) for m in members), 1),
                "gen_mw": round(sum(m.get("gen_mw", 0) for m in members), 1),
            }
        )
    return {
        "point": net.get("point"),
        "bus_count": len(net.get("nodes", [])),
        "line_count": len(net.get("lines", [])),
        "areas": areas,
        "added_loads": net.get("loads", []),
        "added_generators": net.get("generators", []),
        "out_of_service": net.get("out_of_service", {}),
        "warnings": net.get("warnings", []),
        "baseline": baseline_digest(net.get("baseline", {})),
    }


def focus_digest(net: dict[str, Any], focus: str) -> dict[str, Any]:
    """One area (`A06`, or its name) or one bus (`B010`): its buses with load and generation, and lines."""
    key = fold(focus.strip())
    area = next(
        (a for a in net.get("areas", []) if a["id"].lower() == key or key in fold(a.get("name", ""))), None
    )
    node_ids = {n["id"] for n in net.get("nodes", [])}
    if area is None and focus.upper() in node_ids:
        bus_ids = [focus.upper()]
    elif area is not None:
        bus_ids = area.get("buses", [])
    else:
        names = [n["id"] for n in net.get("nodes", []) if key in fold(n.get("name", ""))]
        if not names:
            raise ToolError(
                f"No encuentro '{focus}'. Usa un área ({', '.join(a['id'] for a in net.get('areas', []))}) "
                "o un id de barra B###."
            )
        bus_ids = names[:30]
    wanted = set(bus_ids)
    nodes = {n["id"]: n for n in net.get("nodes", [])}
    rows = [
        {
            "id": b,
            "name": nodes[b].get("name"),
            "kv": nodes[b].get("kv"),
            "area": nodes[b].get("area"),
            "load_mw": net["buses"][b]["load_mw"],
            "gen_mw": net["buses"][b]["gen_mw"],
            "in_service": nodes[b].get("in_service"),
        }
        for b in bus_ids
        if b in nodes
    ]
    lines = [
        {"id": ln["id"], "a": ln["a"], "b": ln["b"], "kv": ln.get("kv"), "capacity_mw": ln.get("capacity_mw")}
        for ln in net.get("lines", [])
        if ln["a"] in wanted or ln["b"] in wanted
    ]
    return {"area": area["id"] if area else None, "buses": rows, "lines": lines[:60]}


def resolve_bus(net: dict[str, Any], text: str) -> str:
    """A bus id from `B###`, an area id or name (its anchor bus) or a unique part of a bus name."""
    nodes = net.get("nodes", [])
    ids = {n["id"] for n in nodes}
    if text.upper() in ids:
        return text.upper()
    key = fold(text.strip())
    for a in net.get("areas", []):
        if a["id"].lower() == key or key in fold(a.get("name", "")):
            return a["anchor_bus"]
    hits = [n["id"] for n in nodes if key and key in fold(n.get("name", ""))]
    if len(hits) == 1:
        return hits[0]
    shown = hits[:10] if hits else [a["id"] for a in net.get("areas", [])]
    raise ToolError(f"No pude elegir una barra para '{text}'. Candidatas o áreas válidas: {shown}")


def snapshot_digest(snap: dict[str, Any]) -> dict[str, Any]:
    m = snap.get("metrics", {})
    return {
        "cycle": snap.get("cycle"),
        "t_min": snap.get("t_min"),
        "demand_mw": m.get("demand_mw"),
        "served_mw": m.get("served_mw"),
        "level": m.get("level") or (snap.get("real") or {}).get("worst_level"),
        "people_without_power": m.get("people_without_power"),
        "observability": m.get("observability"),
        "understood": m.get("understood"),
        "alarms": (snap.get("observed") or {}).get("alarms", []),
        "events": snap.get("events", []),
        "executed": [
            {"action": e.get("action"), "target": e.get("target"), "by": e.get("proposer")}
            for e in snap.get("executed", [])
        ],
        "islands": [island_digest(i) for i in (snap.get("grid") or {}).get("islands", [])],
        "findings": snap.get("findings", []),
    }


def run_digest(run: dict[str, Any]) -> dict[str, Any]:
    keys = ("run_id", "status", "cycle", "horizon", "t_min", "template", "policy", "seed", "operating_point")
    return {k: run[k] for k in keys if k in run}


def report_digest(rep: dict[str, Any]) -> dict[str, Any]:
    ind = rep.get("indicators", {})
    return {
        "run": rep.get("run"),
        "mission": (rep.get("mission") or {}).get("id"),
        "mission_continuity": ind.get("mission_continuity"),
        "priority_continuity": ind.get("priority_continuity"),
        "response_capacity": ind.get("response_capacity"),
        "recoverability_cycles": ind.get("recoverability_cycles"),
        "wrong_decisions": ind.get("wrong_decisions"),
        "consequence": rep.get("consequence"),
        "coordination": rep.get("coordination"),
        "notice": rep.get("notice", NOTICE),
    }
