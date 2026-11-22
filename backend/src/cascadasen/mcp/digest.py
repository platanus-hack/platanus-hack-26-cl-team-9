"""Compact summaries of API responses for the model (docs/mcp.md section 4).

The raw responses are large (188 buses, frames, per-area snapshots). A tool returns only what answers
the question, always with the scenario `notice`, and keeps `is_assumption` on modelled values.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from cascadasen.domain.theater.narrative import LEVELS_ES
from cascadasen.mcp.client import ToolError

NOTICE = "Escenario hipotético: se modela el efecto, no el ataque."


def fold(text: str) -> str:
    """Lowercase without accents, for matching names the user typed."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def bus_place(net: dict[str, Any], bus_id: str | None) -> dict[str, Any]:
    """Where a bus is (name and area), so the model never guesses a bus's location."""
    node: dict[str, Any] = next((n for n in net.get("nodes", []) if n["id"] == bus_id), {})
    area: dict[str, Any] = next((a for a in net.get("areas", []) if a["id"] == node.get("area")), {})
    return {
        "bus": bus_id,
        "bus_name": node.get("name"),
        "area": node.get("area"),
        "area_name": area.get("name"),
    }


def baseline_digest(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_loading": baseline.get("max_loading"),
        "overloaded_lines": baseline.get("overloaded", []),
        "load_shed_mw": baseline.get("load_shed_mw"),
        "islands": len(baseline.get("islands", [])),
    }


def edit_digest(resp: dict[str, Any]) -> dict[str, Any]:
    """Result of an edit: new id, warnings and the redispatch rule, without the per-bus split. The sign is said
    in words: a model repeated "redespacho de -200 MW" without saying who moved."""
    out: dict[str, Any] = {"id": resp.get("id"), "warnings": resp.get("warnings", [])}
    out["redispatch"] = [
        {
            "redispatch_mw": b.get("redispatch_mw"),
            "meaning": redispatch_meaning(b.get("redispatch_mw")),
            "rule": b.get("rule"),
            "is_assumption": b.get("is_assumption"),
        }
        for b in resp.get("balance", [])
    ]
    return out


def redispatch_meaning(mw: Any) -> str | None:
    if not isinstance(mw, int | float) or abs(mw) < 0.05:
        return None
    verb = "suben" if mw > 0 else "bajan"
    return f"las centrales sincrónicas de la isla {verb} {abs(mw):.0f} MW en total para mantener el balance"


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
        "corridors": [{"id": c["id"], "lines": c.get("lines", [])} for c in net.get("corridors", [])],
        "added_loads": [{**item, **bus_place(net, item.get("bus"))} for item in net.get("loads", [])],
        "added_generators": [
            {**item, **bus_place(net, item.get("bus"))} for item in net.get("generators", [])
        ],
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
    overloaded = set((net.get("baseline") or {}).get("overloaded", []))
    return {
        "area": area["id"] if area else None,
        "area_name": area.get("name") if area else None,
        "load_mw": round(sum(r["load_mw"] for r in rows), 1),
        "gen_mw": round(sum(r["gen_mw"] for r in rows), 1),
        "buses": rows,
        "lines": lines[:60],
        "overloaded_lines": sorted(ln["id"] for ln in lines if ln["id"] in overloaded),
    }


def resolve_bus(net: dict[str, Any], text: str, client: Any = None) -> tuple[str, str]:
    """The bus for a place and how it was found. A bus id (also one the session added) or the exact name of a
    bus of this session resolves here; anything else goes to `GET /grids/places`, which knows the comunas and
    the substations that serve them (docs/stress.md section 3). Matching area names first sent "Iquique" to a
    mine 150 km inland, the anchor of the area "Arica–Iquique"."""
    nodes = net.get("nodes", [])
    if text.strip().upper() in {n["id"] for n in nodes}:
        return text.strip().upper(), "barra indicada por id"
    key = fold(text.strip())
    named = [n for n in nodes if fold(n.get("name", "")) in (key, f"s/e {key}")]
    if len(named) == 1:
        return named[0]["id"], f"barra {named[0].get('name')}"
    if client is None:
        raise ToolError(f"No pude elegir una barra para '{text}'. Usa un id B### de describe_network.")
    found = client.get("/grids/places", q=text, point=net.get("point") or "nov2026-1300")
    return found["bus"], found["how"]


# Technology names people use -> the ids the API takes. Nuclear has no plant in Chile: it is modelled as a
# synchronous thermal plant, and the tool says so.
TECH_ALIASES = {
    "eolico": "eolica",
    "eolica": "eolica",
    "viento": "eolica",
    "fotovoltaica": "solar",
    "fotovoltaico": "solar",
    "fv": "solar",
    "pv": "solar",
    "hidroelectrica": "hidro",
    "hidraulica": "hidro",
    "hidrica": "hidro",
    "biomasa": "bioenergia",
    "geotermia": "geotermica",
    "carbon": "carbon",
    "gas natural": "gas",
    "gnl": "gas",
    "petroleo": "diesel",
    "baterias": "bateria",
    "almacenamiento": "bateria",
    "bess": "bateria",
    "nuclear": "termica",
}
NUCLEAR_NOTE = "No hay centrales nucleares en Chile: se modela como térmica sincrónica (supuesto)."


def normalize_tech(tech: str) -> tuple[str, str | None]:
    """The API id of a technology name, and a note when the mapping is an assumption."""
    key = fold(tech.strip())
    note = NUCLEAR_NOTE if key == "nuclear" else None
    return TECH_ALIASES.get(key, key), note


def level_text(level: str | None) -> str | None:
    """The official Spanish label of a consequence level (`narrative.LEVELS_ES`), so the model does not
    invent one."""
    return LEVELS_ES.get(level, level) if level else None


def snapshot_digest(snap: dict[str, Any]) -> dict[str, Any]:
    m = snap.get("metrics", {})
    level = m.get("level") or (snap.get("real") or {}).get("worst_level")
    demand, served = m.get("demand_mw"), m.get("served_mw")
    people = m.get("people_without_power")
    return {
        "cycle": snap.get("cycle"),
        "t_min": snap.get("t_min"),
        "demand_mw": demand,
        "served_mw": served,
        # power not served in this cycle (MW, not energy): computed here so the model does not add MW up
        "unserved_mw": round(demand - served, 1) if demand is not None and served is not None else None,
        "level": level,
        "level_text": level_text(level),
        "people_without_power": round(people) if isinstance(people, float) else people,
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


def events_applied(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Which injected or scripted events happened in these cycles. Said explicitly, with a warning when
    none did, so a summary never claims an event that was not applied."""
    applied = [
        {"cycle": s.get("cycle"), "type": e.get("type"), "target": e.get("target") or e.get("area")}
        for s in snapshots
        for e in s.get("events", [])
    ]
    out: dict[str, Any] = {"events_applied": applied}
    if not applied:
        out["warning"] = (
            "No se aplicó ningún evento en estos ciclos: no digas que ocurrió una apertura o falla. "
            "Si el usuario pidió un evento, inyéctalo con inject_event y vuelve a avanzar."
        )
    return out


def run_digest(run: dict[str, Any]) -> dict[str, Any]:
    keys = ("run_id", "status", "cycle", "horizon", "t_min", "template", "policy", "seed", "operating_point")
    return {k: run[k] for k in keys if k in run}


INCIDENT_NOTICES = [
    "Escenario hipotético: se modela el efecto, no el ataque.",
    "Consecuencia simulada en una red reducida, no una predicción.",
]


def incident_catalog_digest(cat: dict[str, Any]) -> dict[str, Any]:
    return {
        "incidents": [
            {
                **{k: i[k] for k in ("id", "title", "date", "kind", "verified", "notes")},
                "sources": [s["url"] for s in i["sources"]],
                "effects": [f"ciclo {e['cycle']}: {e['type']} en {e['target']}" for e in i["effects"]],
            }
            for i in cat["incidents"]
        ],
        "cost_basis": cat["cost_basis"],
        "notices": cat["notices"],
    }


def report_digest(rep: dict[str, Any]) -> dict[str, Any]:
    ind = rep.get("indicators", {})
    consequence = dict(rep.get("consequence") or {})
    if consequence.get("worst_level"):
        consequence["worst_level_text"] = level_text(consequence["worst_level"])
    return {
        "run": rep.get("run"),
        "mission": (rep.get("mission") or {}).get("id"),
        "mission_continuity": ind.get("mission_continuity"),
        "priority_continuity": ind.get("priority_continuity"),
        "response_capacity": ind.get("response_capacity"),
        "recoverability_cycles": ind.get("recoverability_cycles"),
        "wrong_decisions": ind.get("wrong_decisions"),
        "consequence": consequence,
        "coordination": rep.get("coordination"),
        "notice": rep.get("notice", NOTICE),
        **_incident_digest(rep.get("incident")),
    }


def _incident_digest(inc: dict[str, Any] | None) -> dict[str, Any]:
    if not inc:
        return {}
    keys = ("id", "title", "kind", "verified", "mitigations", "notes", "consequence_card")
    return {"incident": {k: inc[k] for k in keys if k in inc}}


def prepare_digest(out: dict[str, Any]) -> dict[str, Any]:
    """Counts and totals per change, the prepared totals, how many lines start over their limit and the per-zone
    stat; no per-substation ranking (docs/cyber.md section 8.2). A change that touched one to five substations says
    which ones (the person asked for that place), and one that touched none carries a warning, so the model never
    reports a plant that was not built."""
    changes = []
    for c in out["changes"]:
        row = {k: v for k, v in c.items() if k != "elements"}
        elements = c.get("elements") or []
        if 0 < len(elements) <= 5 and not row.get("places"):
            row["at"] = [f"{e.get('id')} {e.get('name')}" for e in elements]
        if c.get("new_substation"):
            new = elements[0]
            row["created"] = (
                f"{new.get('id')} {new.get('name')} ({new.get('kv'):g} kV), conectada a {', '.join(c['connects_to'])}"
            )
        if not c.get("matched"):
            row["warning"] = (
                "Este cambio no tocó ninguna subestación: no digas que se aplicó. Revisa el lugar o la tecnología."
            )
        changes.append(row)
    return {
        "changes": changes,
        "totals": out["totals"],
        "overloaded_lines": len(out["overloaded_lines"]),
        # a model said "8 líneas sobrecargadas, las mismas que en la base" when the base had 1
        "overloaded_lines_note": "Líneas sobre su límite en la red preparada, sin falla. El resultado no dice cuántas "
        "había sin estos cambios: no las compares con la red base.",
        "should_feed_by_zone": out["should_feed"]["by_zone"],
        "per_capita_w": out["per_capita_w"],
        "health": _health_digest(out.get("health")),
        "assumptions": [a["text"] for a in out["assumptions"]],
    }


def _health_digest(h: dict[str, Any] | None) -> dict[str, Any] | None:
    """The prepared grid's health index (0 at the limit, 1 healthy) and the margin that binds it."""
    if not h:
        return None
    return {
        "index": h.get("index"),
        "binding": h.get("binding"),
        "margins": {m["key"]: m["value"] for m in h.get("margins", [])},
    }


def simulation_digest(stressed: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """The cascade of the failures on the prepared grid against the same failures on the base grid, and the
    per-zone supply stat."""
    keys = ("people_without_power", "load_shed_mw", "dark_load_mw")
    return {
        "with_changes": {k: stressed["timeline"]["summary"][k] for k in keys},
        "without_changes": {k: base["timeline"]["summary"][k] for k in keys},
        "lines_opened_by_cascade": sorted(
            {i for e in stressed["timeline"]["events"] if e["type"] == "line_overload_open" for i in e["ids"]}
        ),
        "supply_by_zone": stressed["supply"]["by_zone"],
    }
