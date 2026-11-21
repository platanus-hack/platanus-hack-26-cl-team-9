"""Strategic evaluator (docs/strategy.md section 8). All indicators are experimental proposals.

Per cycle it records continuity, observability, the real-vs-estimated gap, whether ISR understood
the incident, the Freedom of Action Index (validator run on the whole catalog against the real
state, for the evaluator only), resources, decisions and wrong decisions. `report` turns the series
into the final indicators; the Decisional Fragility and Adaptation indices need paired runs and are
computed by the campaign runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.theater.catalog import ACTIONS
from cascadasen.domain.theater.decisions import COA, ISRReport
from cascadasen.domain.theater.state import RealState
from cascadasen.domain.theater.validator import ValidationContext, validate


@dataclass
class CycleMetrics:
    cycle: int
    demand_mw: float
    served_mw: float
    priority_demand_mw: float
    priority_served_mw: float
    observability: float
    estimation_gap: float
    understood: bool
    fai: float
    feasible_coas: int
    resources_remaining: float
    proposals: int
    approved: int
    wrong: int
    level: str
    people_without_power: float

    def as_dict(self) -> dict[str, Any]:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def true_cause(real: RealState) -> str:
    started = [e for e in real.effects if e.established and e.start <= real.cycle]
    if not started:
        return "none"
    return "intentional" if any(e.cause == "intentional" for e in started) else "failure"


def real_affected(real: RealState) -> set[str]:
    g = real.grid
    out = {e.area for e in real.active_effects() if e.area}
    for a in g.load_mw:
        if a in g.blackout_areas or g.served_mw[a] < 0.97 * g.load_mw[a]:
            out.add(a)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def feasible_actions(ctx: ValidationContext) -> int:
    """Safe and viable courses of action now: the whole catalog against the real state."""
    n = 0
    targets = {
        "area": list(ctx.network.order),
        "corridor": list(ctx.network.corridors),
        "defense": list(ctx.defense_areas),
    }
    for spec in ACTIONS.values():
        role = sorted(spec.proposers)[0].value
        kinds = ["area", "corridor"] if spec.id == "restore_element" else [spec.target]
        for kind in kinds:
            for t in targets[kind]:
                if validate(COA(spec.id, t, role, "eval"), ctx).ok:
                    n += 1
    return n


def wrong_decision(real: RealState, coa: COA) -> bool:
    """A non-informational action where nothing real was wrong (or only injected false alarms)."""
    spec = ACTIONS[coa.action]
    if spec.info_only or coa.target not in real.grid.load_mw:
        return False
    g = real.grid
    outage = coa.target in g.blackout_areas or g.served_mw[coa.target] < 0.97 * g.load_mw[coa.target]
    effects = [e for e in real.active_effects(coa.target) if e.event != "D5_false_alarms"]
    return not outage and not effects


@dataclass
class Evaluator:
    priority_areas: tuple[str, ...]
    cycle_hours: float
    voll_usd_per_kwh: float
    series: list[CycleMetrics] = field(default_factory=list)
    onset: int | None = None
    understood_at: int | None = None
    proposals: int = 0
    effective: int = 0
    wrong: int = 0
    baseline_fai: int | None = None

    def record(
        self,
        real: RealState,
        isr: ISRReport | None,
        c2_estimate: dict[str, float],
        ctx: ValidationContext,
        proposals: int,
        approved: int,
        executed_ok: int,
        wrong: int,
        people: float,
    ) -> CycleMetrics:
        g = real.grid
        demand = sum(g.load_mw.values())
        served = sum(g.served_mw.values())
        pd = sum(g.load_mw[a] for a in self.priority_areas if a in g.load_mw)
        ps = sum(g.served_mw[a] for a in self.priority_areas if a in g.served_mw)
        obs = sum(d.health() for d in real.digital.values()) / max(1, len(real.digital))
        gap = sum(abs(g.served_mw[a] - c2_estimate.get(a, 0.0)) / max(g.load_mw[a], 1.0) for a in g.load_mw)
        gap /= max(1, len(g.load_mw))
        affected = real_affected(real)
        cause = true_cause(real)
        if self.onset is None and cause != "none":
            self.onset = real.cycle
        understood = bool(
            isr
            and cause != "none"
            and isr.leading_cause == cause
            and isr.confidence >= 0.7
            and jaccard(set(isr.affected), affected) >= 0.8
        )
        if understood and self.understood_at is None:
            self.understood_at = real.cycle
        feas = feasible_actions(ctx)
        if self.baseline_fai is None:
            self.baseline_fai = max(1, feas)
        self.proposals += proposals
        self.effective += executed_ok
        self.wrong += wrong
        lt = real.last_transient or {}
        m = CycleMetrics(
            cycle=real.cycle,
            demand_mw=demand,
            served_mw=served,
            priority_demand_mw=pd,
            priority_served_mw=ps,
            observability=obs,
            estimation_gap=gap,
            understood=understood,
            fai=feas / self.baseline_fai,
            feasible_coas=feas,
            resources_remaining=ctx.ledger.remaining_fraction(),
            proposals=proposals,
            approved=approved,
            wrong=wrong,
            level=lt.get("level", "L0")
            if lt.get("cycle") == real.cycle
            else ("L1" if served < demand - 1 else "L0"),
            people_without_power=people,
        )
        self.series.append(m)
        return m

    def report(
        self, mission_threshold: float, observability_threshold: float, worst_level: str
    ) -> dict[str, Any]:
        s = self.series
        if not s:
            return {}
        demand = sum(m.demand_mw for m in s)
        served = sum(m.served_mw for m in s)
        mc = served / demand if demand else 1.0
        pd = sum(m.priority_demand_mw for m in s)
        pmc = sum(m.priority_served_mw for m in s) / pd if pd else 1.0
        unserved_mwh = sum(max(0.0, m.demand_mw - m.served_mw) for m in s) * self.cycle_hours
        resistance = 0.0
        for m in s:
            if m.demand_mw and m.served_mw / m.demand_mw >= mission_threshold:
                resistance = max(resistance, m.demand_mw - m.served_mw)
        recover = None
        if self.onset is not None:
            for m in s:
                if (
                    m.cycle > self.onset
                    and m.served_mw >= 0.99 * m.demand_mw
                    and m.observability >= observability_threshold
                ):
                    recover = m.cycle - self.onset
                    break
        ttu = None if self.onset is None or self.understood_at is None else self.understood_at - self.onset
        return {
            "experimental": True,
            "mission_continuity": round(mc, 4),
            "priority_continuity": round(pmc, 4),
            "situational_awareness": {
                "time_to_understanding_cycles": ttu,
                "understood": self.understood_at is not None,
                "onset_cycle": self.onset,
                "mean_estimation_gap": round(sum(m.estimation_gap for m in s) / len(s), 4),
                "mean_observability": round(sum(m.observability for m in s) / len(s), 4),
            },
            "response_capacity": round(self.effective / self.proposals, 4) if self.proposals else None,
            "resistance_mw": round(resistance, 1),
            "operational_reserve": {
                "final": round(s[-1].resources_remaining, 4),
                "minimum": round(min(m.resources_remaining for m in s), 4),
            },
            "recoverability_cycles": recover,
            "wrong_decisions": self.wrong,
            "freedom_of_action_index": {
                "minimum": round(min(m.fai for m in s), 4),
                "final": round(s[-1].fai, 4),
                "mean": round(sum(m.fai for m in s) / len(s), 4),
            },
            "consequence": {
                "worst_level": worst_level,
                "peak_people_without_power": round(max(m.people_without_power for m in s)),
                "unserved_energy_mwh": round(unserved_mwh, 1),
                "failure_cost_usd": round(unserved_mwh * 1000 * self.voll_usd_per_kwh),
            },
        }
