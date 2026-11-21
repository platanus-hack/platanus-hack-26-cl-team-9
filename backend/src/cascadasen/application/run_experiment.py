"""Use cases for strategic runs (docs/stack.md 7.1): create, inject, step, read, replay.

Runs live in an in-memory LRU store (the most recent `max_runs`). Any run can be rebuilt from its
recipe: replaying the same configuration and the same injected events at the same cycles gives the
same hash-chained trace.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import replace
from typing import Any

from cascadasen.domain.ports import CommanderAdvisor, Interpreter
from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.simulation.timeline import NOTICE
from cascadasen.domain.theater.catalog import ACTIONS, EVENTS, OBJECTIVES
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.domain.theater.narrative import TemplateInterpreter
from cascadasen.domain.theater.world import DEFENSES_ID, TheaterWorld

MAX_RUNS = 100


class RunNotFoundError(KeyError):
    pass


class RunManager:
    def __init__(
        self,
        world: TheaterWorld,
        physics: Physics,
        max_runs: int = MAX_RUNS,
        interpreter: Interpreter | None = None,
        advisor: CommanderAdvisor | None = None,
    ) -> None:
        self.world, self.physics, self.max_runs = world, physics, max_runs
        self.runs: OrderedDict[str, Simulation] = OrderedDict()
        self.interpreter = interpreter or TemplateInterpreter()
        self.advisor = advisor  # LLM commander, used only by runs created with llm_commander

    # --------------------------------------------------------------- store

    def _put(self, sim: Simulation) -> str:
        run_id = uuid.uuid4().hex[:12]
        self.runs[run_id] = sim
        while len(self.runs) > self.max_runs:
            self.runs.popitem(last=False)
        return run_id

    def get(self, run_id: str) -> Simulation:
        if run_id not in self.runs:
            raise RunNotFoundError(run_id)
        self.runs.move_to_end(run_id)
        return self.runs[run_id]

    # ------------------------------------------------------------ commands

    def create(self, config: RunConfig, auto_run: bool = False) -> dict[str, Any]:
        sim = Simulation(self.world, config, self.physics, advisor=self.advisor)
        run_id = self._put(sim)
        if auto_run:
            sim.run_to_end()
        return self.summary(run_id)

    def inject(
        self, run_id: str, type_: str, target: str, params: dict[str, Any] | None, cause: str
    ) -> dict[str, Any]:
        return {"run": self.summary(run_id), **self.get(run_id).inject(type_, target, params, cause)}

    def step(self, run_id: str, cycles: int) -> dict[str, Any]:
        snaps = self.get(run_id).step(cycles)
        return {"run": self.summary(run_id), "snapshots": snaps}

    def replay(self, run_id: str, overrides: dict[str, Any], cycles: int | None = None) -> dict[str, Any]:
        """New run with the original seed and injected events (re-injected at their cycles) and
        the given overrides (policy, uncertainty, adversary, capabilities, seed)."""
        original = self.get(run_id)
        if original.config.llm_commander and "llm_choices" not in overrides:
            overrides = {**overrides, "llm_choices": tuple(sorted(original.llm_record.items()))}
        config = replace(original.config, **overrides)
        sim = Simulation(self.world, config, self.physics, advisor=self.advisor)
        new_id = self._put(sim)
        target = cycles if cycles is not None else (original.cycle or sim.horizon)
        by_cycle: dict[int, list[dict[str, Any]]] = {}
        for rec in original.injected:
            by_cycle.setdefault(rec["cycle"], []).append(rec)
        while sim.cycle < min(target, sim.horizon):
            for rec in by_cycle.get(sim.cycle, []):
                sim.inject(rec["type"], rec["target"], rec["params"], rec["cause"])
            sim.step(1)
        return {**self.summary(new_id), "replay_of": run_id, "overrides": overrides}

    # -------------------------------------------------------------- reads

    def summary(self, run_id: str) -> dict[str, Any]:
        sim = self.get(run_id)
        adv = sim.adversary_config
        return {
            "run_id": run_id,
            "status": "finished" if sim.finished else "running",
            "cycle": sim.cycle,
            "horizon": sim.horizon,
            "t_min": sim.cycle * sim.cfg.clock["cycle_minutes"],
            "template": sim.template.id,
            "policy": sim.policy.id,
            "seed": sim.config.seed,
            "uncertainty": sim.config.uncertainty,
            "operating_point": sim.operating_point,
            "defenses": sim.defenses_id,
            "adversary": {
                "enabled": adv.enabled,
                "objective": adv.objective,
                "adaptive": adv.adaptive,
                "budget": adv.budget,
            },
            "notice": NOTICE,
        }

    def state(self, run_id: str) -> dict[str, Any]:
        sim = self.get(run_id)
        return {
            "run": self.summary(run_id),
            "latest": sim.snapshots[-1] if sim.snapshots else None,
            "resources": sim.ledger.snapshot(),
            "series": [s["metrics"] for s in sim.snapshots],
        }

    def snapshots(self, run_id: str, start: int = 0) -> dict[str, Any]:
        """Snapshots already computed from cycle `start` (a replay runs its cycles at once)."""
        sim = self.get(run_id)
        return {"run": self.summary(run_id), "snapshots": sim.snapshots[max(0, start) :]}

    def trace(self, run_id: str) -> dict[str, Any]:
        return self.get(run_id).trace()

    def report(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, **self.get(run_id).report()}

    def after_action(self, run_id: str) -> dict[str, Any]:
        sim = self.get(run_id)
        return {"run_id": run_id, **self.interpreter.after_action(sim.report(), sim.snapshots)}


def catalog(world: TheaterWorld) -> dict[str, Any]:
    """Everything the frontend can choose from: events, actions, policies, objectives, templates."""
    cfg = theater_config()
    return {
        "notice": NOTICE,
        "events": [
            {
                "id": e.id,
                "family": e.family,
                "cyber_class": e.cyber_class,
                "targets": list(e.targets),
                "label_key": e.label_key,
                "defaults": cfg.effects.get(e.id) or {},
            }
            for e in EVENTS.values()
        ],
        "actions": [
            {
                "id": a.id,
                "label_key": a.label_key,
                "proposers": sorted(r.value for r in a.proposers),
                "needs_approval": a.needs_approval,
                "weight": a.weight,
                "target": a.target,
                "reversible": a.reversible,
                "costs": (cfg.actions.get(a.id) or {}).get("costs") or {},
            }
            for a in ACTIONS.values()
        ],
        "policies": [
            {
                "id": p.id,
                "label_key": p.label_key,
                "thresholds": {"light": p.light, "medium": p.medium, "heavy": p.heavy},
                "preventive": p.preventive,
                "reserve_keep": p.reserve_keep,
                "verify_first": p.verify_first,
            }
            for p in cfg.policies.values()
        ],
        "objectives": list(OBJECTIVES),
        "missions": [
            {
                "id": m.id,
                "label_key": m.label_key,
                "priority_areas": list(m.priority_areas),
                "continuity_threshold": m.continuity_threshold,
            }
            for m in cfg.missions.values()
        ],
        "templates": [
            {
                "id": t.id,
                "label_key": t.label_key,
                "question_key": t.question_key,
                "operating_point": t.operating_point,
                "horizon": t.horizon,
                "adversary": {k: v for k, v in t.adversary.items() if k != "plan"},
                "scenario_events": len(t.scenario_events),
            }
            for t in cfg.templates.values()
        ],
        "operating_points": world.points(),
        "defense_sets": [DEFENSES_ID],
        "zones": world.load(world.points()[0])[0].zones if world.points() else [],
        "resources": cfg.resources,
        "uncertainty_levels": {"0": "información perfecta", "1": "línea base", "2": "entorno degradado"},
        "cycle_minutes": cfg.clock["cycle_minutes"],
    }


def run_config(body: dict[str, Any]) -> RunConfig:
    """Build a RunConfig from a plain request body."""
    adv = body.get("adversary")
    return RunConfig(
        template=body.get("template", "open_field"),
        policy=body.get("policy", "C"),
        seed=None if body.get("seed") is None else int(body["seed"]),
        uncertainty=float(body.get("uncertainty", 1.0)),
        horizon=body.get("horizon"),
        adversary=AdversaryConfig(**adv) if adv else None,
        capabilities=tuple(sorted((body.get("capabilities") or {}).items())),
        operating_point=body.get("point") or body.get("operating_point"),
        initial_events=tuple(body.get("initial_events") or ()),
        stochastic=bool(body.get("stochastic", True)),
        llm_commander=bool(body.get("llm_commander", False)),
    )
