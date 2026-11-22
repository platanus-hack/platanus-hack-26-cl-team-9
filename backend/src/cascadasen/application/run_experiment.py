"""Use cases for strategic runs (docs/stack.md 7.1): create, inject, act, step, read, replay.

Every command persists a run record (recipe, cycle, trace head) in a `DocumentStore`, so a run
survives a restart and can be served by another instance. Simulations are kept in a bounded,
process-wide `RunCache` (LRU); a run that is not cached is rebuilt from its record: replaying the
same configuration and the same injected events and actions at the same cycles gives the same
hash-chained trace, which the run reports as `rebuilt` and `trace_matches`.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
import zlib
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from cascadasen.domain.agents.propagation import BOUNDS as PROPAGATION_BOUNDS
from cascadasen.domain.ports import CommanderAdvisor, ConflictError, DocumentStore, Interpreter
from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.simulation.timeline import NOTICE
from cascadasen.domain.theater.catalog import ACTIONS, EVENTS, OBJECTIVES
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.domain.theater.narrative import TemplateInterpreter
from cascadasen.domain.theater.world import DEFENSES_ID, TheaterWorld

MAX_CACHED_RUNS = 20
LOCK_STRIPES = 64
RUN_ID = re.compile(r"^[0-9a-f]{12}$")


class RunNotFoundError(KeyError):
    pass


class RunConflictError(RuntimeError):
    """The run record changed in another instance since this one read it."""


@dataclass
class CachedRun:
    sim: Simulation
    etag: str | None  # etag of the last record written or read; None before the first write
    rebuilt: bool = False
    trace_matches: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None


class RunCache:
    """Process-wide LRU of live simulations, shared by global and session runs (keyed by store key).
    Its striped locks serialise the commands on one run."""

    def __init__(self, max_runs: int = MAX_CACHED_RUNS) -> None:
        self.max_runs = max_runs
        self._runs: OrderedDict[str, CachedRun] = OrderedDict()
        self._guard = threading.Lock()
        self._locks = [threading.Lock() for _ in range(LOCK_STRIPES)]

    def get(self, key: str) -> CachedRun | None:
        with self._guard:
            entry = self._runs.get(key)
            if entry is not None:
                self._runs.move_to_end(key)
            return entry

    def put(self, key: str, entry: CachedRun) -> None:
        with self._guard:
            self._runs[key] = entry
            self._runs.move_to_end(key)
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)

    def evict(self, key: str) -> None:
        with self._guard:
            self._runs.pop(key, None)

    def lock(self, key: str) -> threading.Lock:
        return self._locks[zlib.crc32(key.encode()) % LOCK_STRIPES]

    def __len__(self) -> int:
        return len(self._runs)


class RunManager:
    def __init__(
        self,
        world: TheaterWorld,
        physics: Physics,
        max_runs: int = MAX_CACHED_RUNS,
        interpreter: Interpreter | None = None,
        advisor: CommanderAdvisor | None = None,
        *,
        store: DocumentStore | None = None,
        prefix: str = "runs/",
        cache: RunCache | None = None,
        world_for: Callable[[dict[str, Any]], TheaterWorld] | None = None,
        extra: dict[str, Any] | None = None,
        version: str = "dev",
        clock: Callable[[], float] = time.time,
    ) -> None:
        if store is None:  # one process, nothing configured (tests, scripts)
            from cascadasen.infrastructure.document_store import MemoryDocumentStore

            store = MemoryDocumentStore()
        self.world, self.physics = world, physics
        self.store, self.prefix = store, prefix
        self.cache = cache if cache is not None else RunCache(max_runs)
        self.world_for = world_for  # world of a recorded run (session runs keep their dataset)
        self.extra = extra or {}  # stored with each new run record
        self.version, self.clock = version, clock
        self.interpreter = interpreter or TemplateInterpreter()
        self.advisor = advisor  # LLM commander, used only by runs created with llm_commander

    # --------------------------------------------------------------- store

    def _key(self, run_id: str) -> str:
        return f"{self.prefix}{run_id}.json"

    def _now(self) -> str:
        return datetime.fromtimestamp(self.clock(), UTC).isoformat(timespec="seconds")

    def _load(self, run_id: str) -> CachedRun:
        """The cached run, or the run rebuilt from its record. Call with the run's lock held."""
        if not isinstance(run_id, str) or not RUN_ID.match(run_id):
            raise RunNotFoundError(run_id)
        key = self._key(run_id)
        entry = self.cache.get(key)
        if entry is None:
            found = self.store.get(key)
            if found is None:
                raise RunNotFoundError(run_id)
            entry = self._rebuild(*found)
            self.cache.put(key, entry)
        return entry

    def _persist(self, run_id: str, entry: CachedRun) -> None:
        sim = entry.sim
        record = {
            "run_id": run_id,
            "recipe": sim.recipe(),
            "cycle": sim.cycle,
            "trace_head": sim.log.head,
            "code_version": self.version,
            "created_at": entry.created_at,
            "updated_at": self._now(),
            "extra": entry.extra,
        }
        try:
            entry.etag = self.store.put(
                self._key(run_id), record, if_match=entry.etag, if_none_match=entry.etag is None
            )
        except ConflictError as exc:
            self.cache.evict(self._key(run_id))
            raise RunConflictError(run_id) from exc

    def _new(self, sim: Simulation, extra: dict[str, Any]) -> tuple[str, CachedRun]:
        run_id = uuid.uuid4().hex[:12]
        entry = CachedRun(sim, None, extra=dict(extra), created_at=self._now())
        self.cache.put(self._key(run_id), entry)
        self._persist(run_id, entry)
        return run_id, entry

    @staticmethod
    def _drive(
        sim: Simulation,
        injected: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        target: int,
        pending: bool = False,
    ) -> None:
        """Step `sim` to cycle `target`, re-submitting the recorded events and actions at their
        cycles in their original order. `pending` also re-queues the inputs recorded at `target`
        (accepted but not stepped yet), so a rebuilt run is exactly where it was left."""
        inputs = sorted(
            [((r["cycle"], i, 1, i), "event", r) for i, r in enumerate(injected)]
            + [((r["cycle"], r.get("after_events", 0), 0, j), "action", r) for j, r in enumerate(actions)],
            key=lambda x: x[0],
        )
        by_cycle: dict[int, list[tuple[str, dict[str, Any]]]] = {}
        for (cycle, *_), kind, rec in inputs:
            by_cycle.setdefault(cycle, []).append((kind, rec))

        def submit(cycle: int) -> None:
            for kind, rec in by_cycle.get(cycle, []):
                if kind == "event":
                    sim.inject(rec["type"], rec["target"], rec["params"], rec["cause"])
                else:
                    sim.submit_action(rec["action"], rec["target"], rec["role"], rec["params"], rec["agent"])

        while sim.cycle < min(target, sim.horizon):
            submit(sim.cycle)
            sim.step(1)
        if pending and sim.cycle == target and not sim.finished:
            submit(sim.cycle)

    def _rebuild(self, record: dict[str, Any], etag: str) -> CachedRun:
        recipe = record["recipe"]
        config = RunConfig.from_dict(recipe["config"])
        llm = tuple((int(k), tuple(v)) for k, v in recipe.get("llm_choices") or ())
        if llm:  # recorded LLM picks are replayed verbatim (the run_created entry then differs)
            config = replace(config, llm_choices=llm)
        world = self.world_for(record) if self.world_for else self.world
        sim = Simulation(world, config, self.physics, advisor=self.advisor)
        target = int(recipe.get("cycle", record.get("cycle", 0)))
        self._drive(sim, recipe.get("injected") or [], recipe.get("actions") or [], target, pending=True)
        return CachedRun(
            sim,
            etag,
            rebuilt=True,
            trace_matches=sim.log.head == record.get("trace_head"),
            extra=record.get("extra") or {},
            created_at=record.get("created_at"),
        )

    def get(self, run_id: str) -> Simulation:
        with self.cache.lock(self._key(run_id)):
            return self._load(run_id).sim

    # ------------------------------------------------------------ commands

    def create(self, config: RunConfig, auto_run: bool = False) -> dict[str, Any]:
        sim = Simulation(self.world, config, self.physics, advisor=self.advisor)
        if auto_run:
            sim.run_to_end()
        run_id, entry = self._new(sim, self.extra)
        return self._summary(run_id, entry)

    def _command(self, run_id: str, fn: Callable[[CachedRun], dict[str, Any]]) -> dict[str, Any]:
        with self.cache.lock(self._key(run_id)):
            entry = self._load(run_id)
            out = fn(entry)
            self._persist(run_id, entry)
            return {"run": self._summary(run_id, entry), **out}

    def inject(
        self, run_id: str, type_: str, target: str, params: dict[str, Any] | None, cause: str
    ) -> dict[str, Any]:
        return self._command(run_id, lambda e: e.sim.inject(type_, target, params, cause))

    def action(
        self,
        run_id: str,
        action: str,
        target: str,
        role: str,
        params: dict[str, Any] | None = None,
        agent: str | None = None,
    ) -> dict[str, Any]:
        """Queue an external agent's course of action for the next cycle (validated when it runs)."""
        return self._command(run_id, lambda e: e.sim.submit_action(action, target, role, params, agent))

    def step(self, run_id: str, cycles: int) -> dict[str, Any]:
        return self._command(run_id, lambda e: {"snapshots": e.sim.step(cycles)})

    def replay(self, run_id: str, overrides: dict[str, Any], cycles: int | None = None) -> dict[str, Any]:
        """New run with the original seed, injected events and actions (re-submitted at their cycles)
        and the given overrides (policy, uncertainty, adversary, capabilities, seed)."""
        with self.cache.lock(self._key(run_id)):
            entry = self._load(run_id)
            original = entry.sim
            if original.config.llm_commander and "llm_choices" not in overrides:
                overrides = {**overrides, "llm_choices": tuple(sorted(original.llm_record.items()))}
            config = replace(original.config, **overrides)
            world, cycle = original.world, original.cycle
            injected, actions = list(original.injected), list(original.actions)
        sim = Simulation(world, config, self.physics, advisor=self.advisor)
        target = cycles if cycles is not None else (cycle or sim.horizon)
        self._drive(sim, injected, actions, target)
        new_id, new = self._new(sim, entry.extra)
        return {**self._summary(new_id, new), "replay_of": run_id, "overrides": overrides}

    # -------------------------------------------------------------- reads

    def _read(self, run_id: str, fn: Callable[[CachedRun], Any]) -> Any:
        with self.cache.lock(self._key(run_id)):
            return fn(self._load(run_id))

    def summary(self, run_id: str) -> dict[str, Any]:
        return self._read(run_id, lambda e: self._summary(run_id, e))

    def _summary(self, run_id: str, entry: CachedRun) -> dict[str, Any]:
        sim = entry.sim
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
            "rebuilt": entry.rebuilt,
            "trace_matches": entry.trace_matches,
            "notice": NOTICE,
        }

    def state(self, run_id: str) -> dict[str, Any]:
        def view(e: CachedRun) -> dict[str, Any]:
            sim = e.sim
            return {
                "run": self._summary(run_id, e),
                "latest": sim.snapshots[-1] if sim.snapshots else None,
                "resources": sim.ledger.snapshot(),
                "series": [s["metrics"] for s in sim.snapshots],
            }

        return self._read(run_id, view)

    def snapshots(self, run_id: str, start: int = 0) -> dict[str, Any]:
        """Snapshots already computed from cycle `start` (a replay runs its cycles at once)."""
        return self._read(
            run_id, lambda e: {"run": self._summary(run_id, e), "snapshots": e.sim.snapshots[max(0, start) :]}
        )

    def trace(self, run_id: str) -> dict[str, Any]:
        return self._read(run_id, lambda e: e.sim.trace())

    def report(self, run_id: str) -> dict[str, Any]:
        return self._read(run_id, lambda e: {"run_id": run_id, **e.sim.report()})

    def after_action(self, run_id: str) -> dict[str, Any]:
        def aar(e: CachedRun) -> dict[str, Any]:
            return {"run_id": run_id, **self.interpreter.after_action(e.sim.report(), e.sim.snapshots)}

        return self._read(run_id, aar)


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
        "cyber_attack": _cyber_catalog(cfg, world),
    }


def _cyber_catalog(cfg, world: TheaterWorld) -> dict[str, Any]:
    """What the Ciberataque form needs: defaults and bounds of each parameter, the outcomes, and the
    public area adjacency (operating areas that share a corridor) the intrusion follows."""
    net = world.load(world.points()[0])[0] if world.points() else None
    return {
        "template": "ciberataque",
        "defaults": cfg.cyber_attack,
        "bounds": {k: list(v) for k, v in PROPAGATION_BOUNDS.items()},
        "outcomes": ["attack", "defense", "undecided"],
        "crews_default": cfg.resources.get("field_crews"),
        "adjacency": {a: sorted({c.b if c.a == a else c.a for c in net.incident(a)}) for a in net.order}
        if net
        else {},
        "areas": [{"id": a, "name": net.areas[a].name, "zone": net.areas[a].zone} for a in net.order]
        if net
        else [],
        "is_assumption": True,
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
