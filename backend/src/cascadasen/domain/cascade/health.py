"""Grid health index by margin to the limit (docs/health.md).

Each metric becomes a margin: 1 with room to spare, 0 at its limit, below 0 beyond it (`raw`; `value` is
clipped to 0-1). The index is the **minimum** of the margins flagged `in_index`: the weakest link decides,
a good margin elsewhere does not compensate. It is our own model index, not an official CEN indicator.

Two indices, on different scales, never to be compared with each other:
- `prefault_health`: the operating point before any event (corridor transfer, inertia, loss of the largest
  synchronous unit, single-line cuts with no effect).
- `event_health`: the state after a cut (load served, island frequencies).

Each report also carries the failure cost in `extra["cost"]` (docs/health.md "Cost"): the cost of the event
after a cut, the expected and worst cost of the single-line cuts before one. The cost never enters the index
and the index is never converted to dollars: the index is a minimum of margins, so the two can move apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.simulation.params import load_params, value

from .engine import VOLTAGE_LIMIT, boundary_flow_mw, failure_cost, run_cascade_workflow, zone_load
from .frequency import (
    BLACKOUT_LOW_HZ,
    CENTRO_SUR_STEPS_HZ,
    PARAMS_DIR,
    IslandInput,
    edac_tables,
    simulate_island,
)
from .network import ReducedNetwork
from .scenario import OperatingPoint

_H = load_params("health", PARAMS_DIR)
INERTIA_MIN_MWS = float(value(_H["inertia"]["min_mws"]))
INERTIA_REF_MWS = float(value(_H["inertia"]["ref_mws"]))
NO_EFFECT_MW = float(value(_H["n1"]["no_effect_mw"]))
BAND_LOW_HZ = float(CENTRO_SUR_STEPS_HZ[0])  # first EDAC step: below it the system already sheds load

SRC_CORRIDOR = "[4] rango de validez del esquema de defensa (stack.md 4.6)"
SRC_BLACKOUT = "NTSyCS art. 3-10 (47,5 Hz) y primer escalón EDAC [4] (49,0 Hz)"
SRC_COST = "[19] costo de falla CNE, 8,79 US$/kWh (stack.md 6.1)"
COST_NOTE = "Valoración regulatoria, no pérdida económica medida. Duración del corte supuesta."
TOP_CUTS = 5  # the share of the expected cost carried by the costliest cuts, reported as a band without ids


@dataclass(frozen=True)
class Margin:
    key: str
    label: str
    raw: float  # unclipped: negative when the limit is exceeded
    measured: str  # the measurement behind the margin, for display
    limit: str
    source: str | None = None
    is_assumption: bool = False
    in_index: bool = True
    note: str = ""

    @property
    def value(self) -> float:
        return max(0.0, min(1.0, self.raw))

    def as_dict(self) -> dict[str, Any]:
        out = {
            "key": self.key,
            "label": self.label,
            "value": round(self.value, 3),
            "raw": round(self.raw, 3),
            "measured": self.measured,
            "limit": self.limit,
            "source": self.source,
            "is_assumption": self.is_assumption,
            "in_index": self.in_index,
        }
        if self.note:
            out["note"] = self.note
        return out


@dataclass
class HealthReport:
    kind: str  # "prefault" | "event"
    scenario: str
    margins: list[Margin]
    uncertain: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def index(self) -> float:
        counted = [m.value for m in self.margins if m.in_index]
        return min(counted) if counted else 1.0

    @property
    def binding(self) -> str | None:
        counted = [m for m in self.margins if m.in_index]
        return min(counted, key=lambda m: m.value).key if counted else None

    @property
    def mean(self) -> float:
        counted = [m.value for m in self.margins if m.in_index]
        return sum(counted) / len(counted) if counted else 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "scenario": self.scenario,
            "index": round(self.index, 3),
            "binding": self.binding,
            "mean": round(self.mean, 3),
            "uncertain": self.uncertain,
            "margins": [m.as_dict() for m in self.margins],
            **self.extra,
        }


def corridor_margin(flow_mw: float) -> Margin:
    """25F corridor transfer against the validity range of the defence scheme (+ north to south)."""
    limit = VOLTAGE_LIMIT["limit_ns_mw"] if flow_mw >= 0 else VOLTAGE_LIMIT["limit_sn_mw"]
    sense = "N→S" if flow_mw >= 0 else "S→N"
    return Margin(
        "transfer_25f",
        "Transferencia por el corredor del 25F",
        1.0 - abs(flow_mw) / limit,
        f"{abs(flow_mw):.0f} MW {sense}",
        f"{limit:.0f} MW {sense}",
        source=SRC_CORRIDOR,
    )


def inertia_margin(inertia_mws: float) -> Margin:
    return Margin(
        "inertia",
        "Inercia del sistema",
        (inertia_mws - INERTIA_MIN_MWS) / (INERTIA_REF_MWS - INERTIA_MIN_MWS),
        f"{inertia_mws / 1000:.1f} GVAs",
        f"{INERTIA_MIN_MWS / 1000:.1f} a {INERTIA_REF_MWS / 1000:.1f} GVAs",
        is_assumption=True,
        note="Rango por escenario de la base de operación del CEN, sin re-verificar",
    )


def frequency_margin(net: ReducedNetwork, op: OperatingPoint) -> Margin:
    """Frequency after losing the largest synchronous bus, the whole system as one island.
    ASSUMPTION: the largest synchronous bus stands for the largest single unit."""
    b = int(op.sync_mw.argmax())
    lost = float(op.sync_mw[b])
    sync = float(op.sync_mw.sum() - lost)
    if lost <= 0 or sync <= 0:
        return Margin("frequency_n1", "Frecuencia ante pérdida de la mayor unidad", 0.0, "sin síncronas", "")
    zones = zone_load(net, op.load, list(range(net.size)))
    load = float(op.load.sum())
    island = IslandInput(
        float(op.inertia_mws.sum() - op.inertia_mws[b]),
        sync,
        float(op.gen.sum()) - lost,
        load,
        float(op.gen.sum() - op.sync_mw.sum()),
        zones,
        edac_tables(zones, load),
    )
    sim = simulate_island(island)
    nadir = BLACKOUT_LOW_HZ if sim.outcome == "blackout" else sim.min_hz
    return Margin(
        "frequency_n1",
        "Frecuencia ante pérdida de la mayor unidad",
        (nadir - BLACKOUT_LOW_HZ) / (BAND_LOW_HZ - BLACKOUT_LOW_HZ),
        f"mínimo {nadir:.2f} Hz, RoCoF {sim.rocof_hz_s:.2f} Hz/s, pérdida {lost:.0f} MW",
        f"{BLACKOUT_LOW_HZ} a {BAND_LOW_HZ} Hz",
        source=SRC_BLACKOUT,
        is_assumption=True,
        note="La barra síncrona más grande hace de mayor unidad (supuesto)",
    )


def single_cut_results(net: ReducedNetwork, op: OperatingPoint) -> list[tuple[str, float]]:
    """(line id, load shed in MW) for every single-line cut."""
    return [
        (ln.id, float(run_cascade_workflow(net, op, [ln.id])["summary"]["load_shed_mw"])) for ln in net.lines
    ]


def n1_margins(results: list[tuple[str, float]], total_load_mw: float) -> tuple[Margin, Margin]:
    """Share of single cuts with no effect (in the index) and the worst cut (reported only: cutting a
    reduced line cuts the whole corridor, so the worst cut is an artefact of the reduction)."""
    clean = sum(1 for _, shed in results if shed < NO_EFFECT_MW)
    worst_id, worst = max(results, key=lambda r: r[1], default=("", 0.0))
    return (
        Margin(
            "n1_security",
            "Cortes simples sin efecto (N-1)",
            clean / len(results) if results else 1.0,
            f"{clean} de {len(results)}",
            "todos",
            is_assumption=True,
            note="El corte de una línea reducida corta todo el corredor, no un circuito",
        ),
        Margin(
            "n1_worst",
            "Peor corte simple",
            1.0 - worst / total_load_mw if total_load_mw > 0 else 1.0,
            f"{worst:.0f} MW ({worst_id})",
            "0 MW",
            in_index=False,
            note="Solo informativa: artefacto de la red reducida",
        ),
    )


def _band(share: float, width: int = 20) -> str:
    low = min(int(share * 100) // width * width, 100 - width)
    return f"{low}-{low + width} %"


def n1_cost(results: list[tuple[str, float]]) -> dict[str, Any]:
    """Money at risk in the operating point: the failure cost of every single-line cut, reusing the N-1
    runs of the index. Equal weight per line (ASSUMPTION: no published failure rates per line). The share of
    the costliest cuts is a count and a band, never their ids (cyber.md section 8)."""
    costs = [failure_cost(shed) for _, shed in results]
    usd = sorted((float(c["failure_cost_usd"]) for c in costs), reverse=True)
    total = sum(usd)
    top = min(TOP_CUTS, len(usd))
    outage = costs[0]["outage_duration_h"] if costs else failure_cost(0.0)["outage_duration_h"]
    return {
        "n1_expected_cost_usd": round(total / len(usd)) if usd else 0,
        "n1_worst_cost_usd": round(usd[0]) if usd else 0,
        "n1_cuts": len(usd),
        "n1_cuts_with_cost": sum(1 for u in usd if u > 0),
        "n1_cost_share": {
            "count": top,
            "share_band": _band(sum(usd[:top]) / total) if total > 0 else None,
        },
        "outage_duration_h": outage,
        "is_assumption": True,
        "source": SRC_COST,
        "note": (
            f"{COST_NOTE} Cada línea con el mismo peso (supuesto). El peor corte es un artefacto de la red "
            "reducida: cortar una línea reducida corta todo el corredor."
        ),
    }


def prefault_health(
    net: ReducedNetwork,
    op: OperatingPoint,
    *,
    with_n1: bool = True,
    n1_results: list[tuple[str, float]] | None = None,
) -> HealthReport:
    """Index of the operating point before any event. `n1_results` reuses single-cut runs already made
    (the cache builder runs every cut anyway), so no cut is run twice."""
    margins = [
        corridor_margin(boundary_flow_mw(net, set(), op.gen - op.load)),
        inertia_margin(float(op.inertia_mws.sum())),
        frequency_margin(net, op),
    ]
    extra: dict[str, Any] = {}
    if with_n1:
        results = n1_results if n1_results is not None else single_cut_results(net, op)
        margins.extend(n1_margins(results, float(op.load.sum())))
        extra["cost"] = n1_cost(results)
    return HealthReport("prefault", op.id, margins, extra=extra)


def event_margins(summary: dict) -> tuple[list[Margin], bool]:
    """Margins from a cascade `summary`: load served and island frequencies. A `voltage_limited` island
    gets margin 0 and marks the report uncertain: the 25F voltage collapse is documented, not computed."""
    total = float(summary["load_total_mw"])
    shed = float(summary["load_shed_mw"])
    islands = summary["islands"]
    voltage = any(i["result"] == "voltage_limited" for i in islands)
    hz = []
    for i in islands:
        if i["result"] in ("blackout", "voltage_limited"):
            hz.append(0.0)
        elif i["result"] == "maintains" and i["min_hz"] is not None:
            hz.append((float(i["min_hz"]) - BLACKOUT_LOW_HZ) / (BAND_LOW_HZ - BLACKOUT_LOW_HZ))
    supply = Margin(
        "supply",
        "Demanda servida",
        1.0 - shed / total if total > 0 else 1.0,
        f"{shed:.0f} de {total:.0f} MW perdidos",
        "0 MW perdidos",
    )
    frequency = Margin(
        "frequency_islands",
        "Frecuencia de las islas",
        min(hz) if hz else 1.0,
        "limitada por tensión (incierto)" if voltage else f"{len(hz)} islas evaluadas",
        f"{BLACKOUT_LOW_HZ} a {BAND_LOW_HZ} Hz",
        source=SRC_BLACKOUT,
        note="Una isla limitada por tensión puntúa 0: el colapso de tensión no se calcula",
    )
    return [supply, frequency], voltage or bool(summary.get("uncertain"))


def event_cost(summary: dict, uncertain: bool) -> dict[str, Any]:
    """Failure cost of the event from the same MW lost as the `supply` margin. With an uncertain result
    (a documented, not computed, voltage collapse) the cost is a floor, not an estimate."""
    cost = (
        {k: summary[k] for k in ("failure_cost_usd", "unserved_energy_mwh", "outage_duration_h")}
        if "failure_cost_usd" in summary
        else failure_cost(float(summary["load_shed_mw"]))
    )
    return {
        "cost_usd": cost["failure_cost_usd"],
        "unserved_energy_mwh": cost["unserved_energy_mwh"],
        "outage_duration_h": cost["outage_duration_h"],
        "is_floor": uncertain,
        "source": SRC_COST,
        "note": COST_NOTE,
    }


def event_report(summary: dict, scenario: str, cut: list[str]) -> HealthReport:
    """Index and cost of the state described by a cascade `summary` (no new run)."""
    margins, uncertain = event_margins(summary)
    return HealthReport(
        "event",
        scenario,
        margins,
        uncertain,
        {"cut": cut, "stages": summary.get("stages"), "cost": event_cost(summary, uncertain)},
    )


def event_health(net: ReducedNetwork, op: OperatingPoint, cut_line_ids: list[str]) -> HealthReport:
    """Index of the state after cutting `cut_line_ids`."""
    return event_report(run_cascade_workflow(net, op, cut_line_ids)["summary"], op.id, cut_line_ids)


__all__ = [
    "HealthReport",
    "Margin",
    "corridor_margin",
    "event_cost",
    "event_health",
    "event_margins",
    "event_report",
    "frequency_margin",
    "inertia_margin",
    "n1_cost",
    "n1_margins",
    "prefault_health",
]
