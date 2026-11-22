"""Consequence card and public metadata of a documented-incident run (docs/attack-sim.md).

Only the effect is modelled (cyber.md 8). Unserved energy and cost are the cascade engine's own
(`blackout_cost`, docs/engine.md "Cost"): dark demand needs a black start (hours and a total-blackout premium
from the 25F study [44]) and load shed in a surviving island is back in about an hour (an assumption). The card
takes the most expensive cascade of the run, so it equals what "Estado de la red" shows for the same event.
"""

from __future__ import annotations

from typing import Any

from cascadasen.domain.cascade.frequency import cascade_params
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


def cost_basis() -> dict[str, Any]:
    """The calibrated cost terms with their source or `is_assumption`, as the engine reads them."""
    return {
        k: {
            "value": v["value"],
            "source": v.get("source"),
            "is_assumption": bool(v.get("is_assumption", False)),
        }
        for k, v in cascade_params()["cost"].items()
    }


def incident_card(
    inc: Incident, series: list[Any], worst_level: str, cascades: list[dict[str, Any]]
) -> dict[str, Any]:
    """`cascades`: the engine summaries of the cycles that ran a cascade (`transient.summary`)."""
    worst = max(cascades, key=lambda c: c.get("failure_cost_usd", 0), default=None)
    peak_mw = max((max(0.0, m.demand_mw - m.served_mw) for m in series), default=0.0)
    cost = {
        "unserved_energy_mwh": worst["unserved_energy_mwh"] if worst else 0.0,
        "failure_cost_usd": worst["failure_cost_usd"] if worst else 0,
        "cost_per_hour_usd": worst["cost_per_hour_usd"] if worst else 0,
        "outage_duration_h": worst["outage_duration_h"] if worst else {"value": 0, "is_assumption": False},
        "cost_breakdown": worst["cost_breakdown"] if worst else {},
    }
    return {
        "incident": inc.id,
        "consequence_level": worst_level,
        "people_without_power": round(max((m.people_without_power for m in series), default=0.0)),
        "load_shed_mw": round(peak_mw, 1),
        **cost,
        "cost_basis": cost_basis(),
        "note": "Costo de falla del motor de cascadas (CNE 8,79 US$/kWh), el mismo de Estado de la red: la carga "
        "apagada paga un arranque en negro y un recargo por apagón total; el deslastre, una hora.",
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
        "cost_basis": cost_basis(),
        "incidents": items,
    }
