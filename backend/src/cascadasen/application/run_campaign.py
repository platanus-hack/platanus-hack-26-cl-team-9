"""Campaigns of strategic experiments (docs/strategy.md sections 7-8).

A campaign runs a matrix of runs and compares them under equivalent conditions:

- Mode I, diagnostic: scenarios without an adaptive adversary. Shows where continuity is lost, by
  area in geographic order (never sorted as a ranking).
- Mode II, adversarial: policies x uncertainty x {static, adaptive} adversary. Computes the
  Decisional Fragility Index (paired runs at uncertainty 0 are added automatically) and the
  Adaptation Index (adaptive vs static on the same seeds).
- Mode III, capability: capability variants x policies, against the adaptive adversary. Reports
  the change of each indicator against the first (baseline) variant.

Runs are synchronous and bounded (`MAX_RUNS`).
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.simulation.network import ReducedNetwork
from cascadasen.domain.simulation.timeline import NOTICE
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, RunInputError, Simulation

MODES = ("diagnostic", "adversarial", "capability")
MAX_RUNS = 240
MAX_CAMPAIGNS = 20


class CampaignNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class CampaignSpec:
    mode: str = "adversarial"
    templates: tuple[str, ...] = ("flagship_observability",)
    policies: tuple[str, ...] = ("A", "B", "C")
    seeds: tuple[int, ...] = (1, 2, 3)
    uncertainty_levels: tuple[float, ...] = (1.0,)
    adversary_variants: tuple[str, ...] = ("static", "adaptive")
    capability_variants: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = ()
    horizon: int | None = None
    objective: str | None = None
    budget: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "templates": list(self.templates),
            "policies": list(self.policies),
            "seeds": list(self.seeds),
            "uncertainty_levels": list(self.uncertainty_levels),
            "adversary_variants": list(self.adversary_variants),
            "capability_variants": [{"id": i, "capabilities": dict(c)} for i, c in self.capability_variants],
            "horizon": self.horizon,
            "objective": self.objective,
            "budget": self.budget,
        }


@dataclass
class Cell:
    template: str
    policy: str
    uncertainty: float
    adversary: str
    capability: str
    reports: list[dict[str, Any]] = field(default_factory=list)
    area_continuity: list[dict[str, float]] = field(default_factory=list)


def _avg(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 4) if vals else None


def _row(c: Cell) -> dict[str, Any]:
    ind = [r["indicators"] for r in c.reports]
    con = [r["consequence"] for r in c.reports]
    coord = [r["coordination"] for r in c.reports]
    return {
        "template": c.template,
        "policy": c.policy,
        "uncertainty": c.uncertainty,
        "adversary": c.adversary,
        "capability": c.capability,
        "runs": len(c.reports),
        "mission_continuity": _avg([i["mission_continuity"] for i in ind]),
        "priority_continuity": _avg([i["priority_continuity"] for i in ind]),
        "time_to_understanding_cycles": _avg(
            [i["situational_awareness"]["time_to_understanding_cycles"] for i in ind]
        ),
        "understood_share": _avg([1.0 if i["situational_awareness"]["understood"] else 0.0 for i in ind]),
        "estimation_gap": _avg([i["situational_awareness"]["mean_estimation_gap"] for i in ind]),
        "response_capacity": _avg([i["response_capacity"] for i in ind]),
        "wrong_decisions": _avg([i["wrong_decisions"] for i in ind]),
        "operational_reserve_final": _avg([i["operational_reserve"]["final"] for i in ind]),
        "recoverability_cycles": _avg([i["recoverability_cycles"] for i in ind]),
        "freedom_of_action_min": _avg([i["freedom_of_action_index"]["minimum"] for i in ind]),
        "conflicts": _avg([c_["conflicts"] for c_ in coord]),
        "unserved_energy_mwh": _avg([x["unserved_energy_mwh"] for x in con]),
        "failure_cost_usd": _avg([x["failure_cost_usd"] for x in con]),
    }


class CampaignRunner:
    def __init__(self, network: ReducedNetwork, physics: Physics) -> None:
        self.network, self.physics = network, physics
        self.campaigns: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def get(self, campaign_id: str) -> dict[str, Any]:
        if campaign_id not in self.campaigns:
            raise CampaignNotFoundError(campaign_id)
        return self.campaigns[campaign_id]

    def _validate(self, spec: CampaignSpec) -> list[float]:
        cfg = theater_config()
        if spec.mode not in MODES:
            raise RunInputError("mode", "modo desconocido", list(MODES))
        for t in spec.templates:
            if t not in cfg.templates:
                raise RunInputError(
                    "templates", f"{t}: plantilla desconocida", sorted(cfg.templates), not_found=True
                )
        for p in spec.policies:
            if p not in cfg.policies:
                raise RunInputError("policies", f"{p}: política desconocida", sorted(cfg.policies))
        for v in spec.adversary_variants:
            if v not in ("none", "static", "adaptive"):
                raise RunInputError(
                    "adversary_variants", f"{v}: variante desconocida", ["none", "static", "adaptive"]
                )
        if not spec.seeds or not spec.policies or not spec.templates:
            raise RunInputError("seeds", "se necesita al menos una semilla, una política y una plantilla")
        levels = list(spec.uncertainty_levels)
        if spec.mode == "adversarial" and any(u > 0 for u in levels) and 0.0 not in levels:
            levels = [0.0, *levels]  # paired perfect-information runs for the fragility index
        variants = spec.capability_variants or (("baseline", ()),)
        n = (
            len(spec.templates)
            * len(spec.policies)
            * len(spec.seeds)
            * len(levels)
            * len(self._adversaries(spec))
            * len(variants)
        )
        if n > MAX_RUNS:
            raise RunInputError("campaign", f"{n} corridas: el máximo es {MAX_RUNS}")
        return levels

    @staticmethod
    def _adversaries(spec: CampaignSpec) -> tuple[str, ...]:
        if spec.mode == "diagnostic":
            return ("static",) if "static" in spec.adversary_variants else ("none",)
        if spec.mode == "capability":
            return ("adaptive",)
        return spec.adversary_variants

    def _adversary(self, template_id: str, variant: str, spec: CampaignSpec) -> AdversaryConfig:
        t = theater_config().template(template_id)
        objective = spec.objective or t.adversary.get("objective", "reduce_observability")
        budget = spec.budget if spec.budget is not None else float(t.adversary.get("budget", 8) or 8)
        return AdversaryConfig(
            enabled=variant != "none", objective=objective, budget=budget, adaptive=variant == "adaptive"
        )

    def run(self, spec: CampaignSpec) -> dict[str, Any]:
        levels = self._validate(spec)
        started = time.perf_counter()
        variants = spec.capability_variants or (("baseline", ()),)
        cells: dict[tuple, Cell] = {}
        for template in spec.templates:
            for policy in spec.policies:
                for u in levels:
                    for adv in self._adversaries(spec):
                        for cap_id, caps in variants:
                            cell = Cell(template, policy, u, adv, cap_id)
                            cells[(template, policy, u, adv, cap_id)] = cell
                            for seed in spec.seeds:
                                sim = Simulation(
                                    self.network,
                                    RunConfig(
                                        template=template,
                                        policy=policy,
                                        seed=seed,
                                        uncertainty=u,
                                        horizon=spec.horizon,
                                        adversary=self._adversary(template, adv, spec),
                                        capabilities=caps,
                                    ),
                                    self.physics,
                                )
                                sim.run_to_end()
                                cell.reports.append(sim.report())
                                cell.area_continuity.append(self._area_continuity(sim))
        result = {
            "mode": spec.mode,
            "spec": spec.as_dict(),
            "runs": sum(len(c.reports) for c in cells.values()),
            "elapsed_s": round(time.perf_counter() - started, 2),
            "question_keys": sorted({theater_config().template(t).question_key for t in spec.templates}),
            "notice": NOTICE,
            "experimental": True,
            "table": [_row(c) for c in cells.values()],
            "indices": self._indices(cells),
        }
        if spec.mode == "diagnostic":
            result["areas"] = self._areas(cells)
        if spec.mode == "capability":
            result["capability_deltas"] = self._deltas(result["table"], variants[0][0])
        campaign_id = uuid.uuid4().hex[:12]
        result["campaign_id"] = campaign_id
        self.campaigns[campaign_id] = result
        while len(self.campaigns) > MAX_CAMPAIGNS:
            self.campaigns.popitem(last=False)
        return result

    def _area_continuity(self, sim: Simulation) -> dict[str, float]:
        served = {a: 0.0 for a in self.network.order}
        demand = {a: 0.0 for a in self.network.order}
        for s in sim.snapshots:
            for a, v in s["real"]["areas"].items():
                served[a] += v["served_mw"]
                demand[a] += v["demand_mw"]
        return {a: served[a] / demand[a] if demand[a] else 1.0 for a in self.network.order}

    def _areas(self, cells: dict[tuple, Cell]) -> list[dict[str, Any]]:
        """Continuity per area in geographic order (north to south), averaged over the campaign."""
        rows = []
        for a in self.network.order:
            vals = [ac[a] for c in cells.values() for ac in c.area_continuity]
            rows.append({"area": a, "name": self.network.areas[a].name, "continuity": _avg(vals)})
        return rows

    @staticmethod
    def _mc(cells: dict[tuple, Cell], **key: Any) -> float | None:
        vals = [
            r["indicators"]["mission_continuity"]
            for k, c in cells.items()
            if all(getattr(c, f) == v for f, v in key.items())
            for r in c.reports
        ]
        return mean(vals) if vals else None

    def _indices(self, cells: dict[tuple, Cell]) -> dict[str, Any]:
        fragility, adaptation = [], []
        combos = {(c.template, c.policy, c.adversary, c.capability) for c in cells.values()}
        levels = sorted({c.uncertainty for c in cells.values()})
        for template, policy, adv, cap in sorted(combos):
            perfect = self._mc(
                cells, template=template, policy=policy, adversary=adv, capability=cap, uncertainty=0.0
            )
            for u in levels:
                if u <= 0 or perfect in (None, 0):
                    continue
                degraded = self._mc(
                    cells, template=template, policy=policy, adversary=adv, capability=cap, uncertainty=u
                )
                if degraded is not None:
                    fragility.append(
                        {
                            "template": template,
                            "policy": policy,
                            "adversary": adv,
                            "capability": cap,
                            "uncertainty": u,
                            "value": round((perfect - degraded) / perfect, 4),
                        }
                    )
        pairs = {(c.template, c.policy, c.uncertainty, c.capability) for c in cells.values()}
        for template, policy, u, cap in sorted(pairs):
            adaptive = self._mc(
                cells, template=template, policy=policy, uncertainty=u, capability=cap, adversary="adaptive"
            )
            static = self._mc(
                cells, template=template, policy=policy, uncertainty=u, capability=cap, adversary="static"
            )
            if adaptive is not None and static:
                adaptation.append(
                    {
                        "template": template,
                        "policy": policy,
                        "uncertainty": u,
                        "capability": cap,
                        "value": round(adaptive / static, 4),
                    }
                )
        return {"decisional_fragility": fragility, "adaptation": adaptation}

    @staticmethod
    def _deltas(table: list[dict[str, Any]], baseline: str) -> list[dict[str, Any]]:
        keys = (
            "mission_continuity",
            "priority_continuity",
            "time_to_understanding_cycles",
            "wrong_decisions",
            "operational_reserve_final",
            "unserved_energy_mwh",
        )
        base = {
            (r["template"], r["policy"], r["uncertainty"]): r for r in table if r["capability"] == baseline
        }
        out = []
        for r in table:
            b = base.get((r["template"], r["policy"], r["uncertainty"]))
            if r["capability"] == baseline or b is None:
                continue
            out.append(
                {
                    "capability": r["capability"],
                    "template": r["template"],
                    "policy": r["policy"],
                    "uncertainty": r["uncertainty"],
                    **{k: (None if r[k] is None or b[k] is None else round(r[k] - b[k], 4)) for k in keys},
                }
            )
        return out
