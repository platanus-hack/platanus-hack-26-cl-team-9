"""Consequence card and public metadata of a documented-incident run (docs/attack-sim.md).

Only the effect is modelled (cyber.md 8). The outage duration scales unserved energy and cost: the
theatre horizon is about two hours, a real interruption lasts longer, so the card extrapolates the
peak shed power over `duration_h`, which is an assumption and editable per run.
"""

from __future__ import annotations

from typing import Any

from cascadasen.domain.simulation.consequence import outage_cost
from cascadasen.domain.theater.config import Incident

NOTICES = (
    "Escenario hipotético: se modela el efecto, no el ataque.",
    "Consecuencia simulada en una red reducida, no una predicción.",
)


def incident_public(
    inc: Incident, scenario_events: int, horizon: int, operating_point: str
) -> dict[str, Any]:
    return {
        "id": inc.id,
        "title": inc.title,
        "date": inc.date,
        "kind": inc.kind,
        "verified": inc.verified,
        "sources": [dict(s) for s in inc.sources],
        "notes": list(inc.notes),
        "mitigations": list(inc.mitigations),
        "summary_key": inc.summary_key,
        "operating_point": operating_point,
        "horizon": horizon,
        "scenario_events": scenario_events,
        "adversary": False,
        "notices": list(NOTICES),
    }


def incident_card(
    inc: Incident,
    series: list[Any],
    worst_level: str,
    voll_usd_per_kwh: float,
    duration_h: float,
    duration_is_assumption: bool,
) -> dict[str, Any]:
    peak_mw = max((max(0.0, m.demand_mw - m.served_mw) for m in series), default=0.0)
    cost = outage_cost(peak_mw, duration_h, duration_is_assumption, voll_usd_per_kwh)
    return {
        "incident": inc.id,
        "consequence_level": worst_level,
        "people_without_power": round(max((m.people_without_power for m in series), default=0.0)),
        "load_shed_mw": round(peak_mw, 1),
        **cost,
        "note": "MWh y costo extrapolan la potencia no servida máxima durante la duración indicada.",
        "notices": list(NOTICES),
    }


def incident_catalog(cfg: Any) -> dict[str, Any]:
    """The bounded catalog, in the order of the file. No ranking and no sweep (cyber.md 8)."""
    items = []
    for inc in cfg.incidents.values():
        t = cfg.templates[inc.id]
        items.append(
            {
                **incident_public(inc, len(t.scenario_events), t.horizon, t.operating_point),
                "effects": [
                    {
                        "cycle": e.get("cycle", 0),
                        "type": e["type"],
                        "target": e["target"],
                        "params": e.get("params") or {},
                    }
                    for e in t.scenario_events
                ],
                "label_key": t.label_key,
                "question_key": t.question_key,
            }
        )
    return {
        "notices": list(NOTICES),
        "default_duration_h": {"value": cfg.incident_duration_h, "is_assumption": True},
        "incidents": items,
    }
