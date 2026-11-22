"""Strategic cycle (docs/strategy.md section 7): one run of the cyber-physical theatre.

Each operational cycle:
    0. tick: effects expire, segmentation and external support finish, restorations progress
    1. events: scenario, user injections and the adversary act on the real state (one transient)
    2. observe: the digital engine turns the real state into what supervision shows
    3. understand (ISR), intent (C2), plan (Operations, Stabilisation, Logistics)
    4. validate (deterministic) and decide (C2, within attention), with vetoes
    5. execute approved actions and queued external agent actions (re-validated) on the real state
    6. evaluate (indicators, Auditor findings) and adapt (adversary learns)
Everything is appended to a hash-chained audit log. A run is reproducible from its recipe
(configuration, seed, injected events and external actions with their cycle).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, cast

from cascadasen.domain.agents.adversary import AdversaryAgent
from cascadasen.domain.agents.auditor import AuditorAgent, CycleRecord
from cascadasen.domain.agents.base import AdversaryView, AgentView
from cascadasen.domain.agents.commander import CommanderAgent
from cascadasen.domain.agents.isr import ISRAgent
from cascadasen.domain.agents.logistics import LogisticsAgent
from cascadasen.domain.agents.operations import OperationsAgent
from cascadasen.domain.agents.stabilization import StabilizationAgent
from cascadasen.domain.ports import CommanderAdvisor
from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.simulation.timeline import NOTICE
from cascadasen.domain.theater.areas import bus_id
from cascadasen.domain.theater.audit import AuditLog
from cascadasen.domain.theater.catalog import ACTIONS, EVENTS, OBJECTIVES
from cascadasen.domain.theater.config import TheaterConfig, theater_config
from cascadasen.domain.theater.crews import CrewRoster
from cascadasen.domain.theater.decisions import COA, ActionFeedback, Decision
from cascadasen.domain.theater.digital import observe
from cascadasen.domain.theater.evaluator import Evaluator, real_affected, wrong_decision
from cascadasen.domain.theater.execution import (
    EventError,
    EventRequest,
    ExecutionState,
    Executor,
    UnknownEventTargetError,
)
from cascadasen.domain.theater.grid import TheaterGrid
from cascadasen.domain.theater.incident import incident_card, incident_public
from cascadasen.domain.theater.resources import Ledger
from cascadasen.domain.theater.rng import new_seed, rng_for
from cascadasen.domain.theater.state import AreaDigital, ObservedState, RealState
from cascadasen.domain.theater.stochastic import Chance
from cascadasen.domain.theater.validator import ValidationContext, costs_of, validate
from cascadasen.domain.theater.world import DEFENSES_ID, TheaterWorld

UNCERTAINTY_RANGE = (0.0, 2.0)


class RunInputError(ValueError):
    """Invalid run input: HTTP 422, or 404 when it names something that does not exist."""

    def __init__(
        self, field: str, message: str, valid: list[str] | None = None, not_found: bool = False
    ) -> None:
        super().__init__(message)
        self.field, self.message, self.valid, self.not_found = field, message, valid or [], not_found

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {"field": self.field, "message": self.message}
        if self.valid:
            out["valid"] = self.valid
        return out


class RunFinishedError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdversaryConfig:
    enabled: bool = False
    objective: str = "reduce_observability"
    budget: float = 8.0
    adaptive: bool = True


@dataclass(frozen=True)
class RunConfig:
    template: str = "open_field"
    policy: str = "C"
    seed: int | None = None  # None: a fresh random seed, recorded in the recipe
    uncertainty: float = 1.0
    horizon: int | None = None
    adversary: AdversaryConfig | None = None
    capabilities: tuple[tuple[str, float], ...] = ()
    operating_point: str | None = None  # a mapa 3 point id (nov2026-1300, feb2025-1500...)
    initial_events: tuple[dict[str, Any], ...] = ()
    stochastic: bool = True  # False: catalog sizes, no unplanned events, actions always work
    llm_commander: bool = False  # C2 picks among validated COAs with the configured LLM advisor
    llm_choices: tuple[tuple[int, tuple[str, ...]], ...] = ()  # recorded picks, replayed verbatim

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["capabilities"] = dict(self.capabilities)
        d["initial_events"] = [dict(e) for e in self.initial_events]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunConfig:
        """Inverse of `as_dict`, also after a JSON round trip (a persisted recipe)."""
        adv = d.get("adversary")
        return cls(
            template=d.get("template", "open_field"),
            policy=d.get("policy", "C"),
            seed=None if d.get("seed") is None else int(d["seed"]),
            uncertainty=float(d.get("uncertainty", 1.0)),
            horizon=d.get("horizon"),
            adversary=AdversaryConfig(**adv) if adv else None,
            capabilities=tuple(sorted((d.get("capabilities") or {}).items())),
            operating_point=d.get("operating_point"),
            initial_events=tuple(dict(e) for e in d.get("initial_events") or ()),
            stochastic=bool(d.get("stochastic", True)),
            llm_commander=bool(d.get("llm_commander", False)),
            llm_choices=tuple((int(k), tuple(v)) for k, v in d.get("llm_choices") or ()),
        )


@dataclass
class Simulation:
    world: TheaterWorld
    config: RunConfig
    physics: Physics = field(default_factory=Physics.load)
    cfg: TheaterConfig = field(default_factory=theater_config)
    advisor: CommanderAdvisor | None = None  # used only when config.llm_commander
    light: bool = False  # campaigns: skip the per-cycle map frame (no effect on the run itself)

    def __post_init__(self) -> None:
        """Build the whole run from `config` and the world, without simulating any cycle.

        Order: a fresh seed when none was given (stored in `config`, so the recipe replays the run), config
        validation, template and horizon, the adversary config (the request's, else the template's), the
        operating point (`RunInputError` when unknown) and its network, the real state, the resource ledger
        (catalog resources plus the requested capabilities), the agents, and last the scheduled events (scenario
        first, then the user's), each checked by `_check_event` and indexed by cycle. All randomness comes from
        named streams of the seed (`Chance`, `rng_for`), so the same config and seed give the same run. Writes
        the first audit entry, `run_created`. `light` only skips the per-cycle map frame."""
        if self.config.seed is None:
            self.config = replace(self.config, seed=new_seed())
        cfg, conf = self.cfg, self.config
        self._validate_config()
        self.template = cfg.template(conf.template)
        self.horizon = conf.horizon or self.template.horizon
        adv = conf.adversary or AdversaryConfig(
            enabled=bool(self.template.adversary.get("enabled")),
            objective=self.template.adversary.get("objective", "reduce_observability"),
            budget=float(self.template.adversary.get("budget", cfg.adversary["budget"])),
            adaptive=bool(self.template.adversary.get("adaptive", True)),
        )
        self.adversary_config = adv
        self.operating_point = conf.operating_point or self.template.operating_point
        if self.operating_point not in self.world.points():
            raise RunInputError(
                "operating_point", "punto de operación desconocido", sorted(self.world.points())
            )
        self.network, base_point = self.world.load(self.operating_point)
        net = self.network
        self.defenses_id = DEFENSES_ID
        self.mission = cfg.missions[self.template.mission]
        self.policy = cfg.policies[conf.policy]
        grid = TheaterGrid.from_point(net, base_point)
        self.plan_load = dict(grid.load_mw)
        self.real = RealState(0, grid, {a: AreaDigital() for a in net.order})
        self.ledger = Ledger({**cfg.resources, **dict(conf.capabilities)})
        self.defense_areas = net.defense_areas()
        self.chance = (
            Chance.for_run(cast(int, conf.seed), cfg.stochastic)
            if conf.stochastic and cfg.stochastic
            else None
        )
        self.executor = Executor(net, cfg, self.defense_areas, self.chance)
        self.ex = ExecutionState()
        self.log = AuditLog()
        self.isr = ISRAgent(net, cfg.isr)
        self.c2 = CommanderAgent(net, self.plan_load)
        self.ops = OperationsAgent(net)
        self.stab = StabilizationAgent(net, self.plan_load, self.defense_areas)
        self.crew_actions = frozenset(
            a for a, spec in cfg.actions.items() if (spec.get("costs") or {}).get("field_crews")
        )
        self.roster = (
            CrewRoster.build(
                net,
                int(self.ledger.capacity.get("field_crews", 0)),
                cfg.crews,
                cfg.clock["cycle_minutes"],
                rng=self.chance.field if self.chance else None,
            )
            if cfg.crews
            else None
        )
        self.logistics = LogisticsAgent(
            net, self.crew_actions, cfg.crews.get("max_eta_cycles"), self.defense_areas
        )
        self.auditor = AuditorAgent()
        self.adversary: AdversaryAgent | None = None
        if adv.enabled:
            self.adversary = AdversaryAgent(
                targets={
                    "area": list(net.order),
                    "zone": list(net.zones),
                    "defense": sorted(self.defense_areas),
                },
                objective=adv.objective,
                budget=adv.budget,
                adaptive=adv.adaptive,
                plan=list(self.template.adversary.get("plan") or []),
                rng=rng_for(cast(int, conf.seed), "adversary"),
                catalog=cfg.adversary,
            )
        self.evaluator = Evaluator(
            self.mission.priority_areas, cfg.clock["cycle_minutes"] / 60.0, self.physics.voll_usd_per_kwh
        )
        self.rng_digital = rng_for(cast(int, conf.seed), "digital")
        self.history_real = [self._real_snapshot()]
        self.observations: list[ObservedState] = []
        self.snapshots: list[dict[str, Any]] = []
        self.injected: list[dict[str, Any]] = []
        self.queue: list[EventRequest] = []
        self.actions: list[dict[str, Any]] = []  # external agent actions, as recorded in the recipe
        self.action_queue: list[COA] = []
        self.feedback: list[ActionFeedback] = []
        self.cycle = 0
        self.llm_record: dict[int, tuple[str, ...]] = dict(conf.llm_choices)
        self.llm_note: dict[str, Any] | None = None
        self.effect_seq = 0
        self.scheduled: dict[int, list[EventRequest]] = {}
        sources = [("scenario", e) for e in self.template.scenario_events]
        sources += [("user", e) for e in conf.initial_events]
        for source, e in sources:
            req = EventRequest(
                e["type"],
                e["target"],
                tuple((e.get("params") or {}).items()),
                source,
                e.get("cause", "intentional"),
            )
            self._check_event(req)
            self.scheduled.setdefault(int(e.get("cycle", 0)), []).append(req)
        self.log.append(
            0,
            "setup",
            "engine",
            "run_created",
            {
                "config": conf.as_dict(),
                "horizon": self.horizon,
                "operating_point": self.operating_point,
                "defenses": self.defenses_id,
                "mission": self.mission.id,
                "policy": self.policy.id,
                "adversary": asdict(adv),
            },
        )

    # ------------------------------------------------------------ validation

    def _validate_config(self) -> None:
        cfg, conf = self.cfg, self.config
        if conf.template not in cfg.templates:
            raise RunInputError("template", "plantilla desconocida", sorted(cfg.templates), not_found=True)
        if conf.policy not in cfg.policies:
            raise RunInputError("policy", "política desconocida", sorted(cfg.policies))
        lo, hi = UNCERTAINTY_RANGE
        if not lo <= conf.uncertainty <= hi:
            raise RunInputError("uncertainty", f"entre {lo:g} y {hi:g}")
        if conf.horizon is not None and not 1 <= conf.horizon <= cfg.clock["max_horizon"]:
            raise RunInputError("horizon", f"entre 1 y {cfg.clock['max_horizon']} ciclos")
        if conf.adversary and conf.adversary.objective not in OBJECTIVES:
            raise RunInputError("adversary.objective", "objetivo desconocido", list(OBJECTIVES))
        if conf.adversary and not 0 <= conf.adversary.budget <= 50:
            raise RunInputError("adversary.budget", "entre 0 y 50")
        for pool, cap in conf.capabilities:
            if pool not in cfg.resources:
                raise RunInputError("capabilities", f"{pool}: recurso desconocido", sorted(cfg.resources))
            if not 0 <= cap <= 10_000:
                raise RunInputError("capabilities", f"{pool}: entre 0 y 10000")

    def _check_event(self, req: EventRequest) -> tuple[str, str | None]:
        try:
            return self.executor.resolve(req)
        except UnknownEventTargetError as exc:
            raise RunInputError("target", str(exc), not_found=True) from exc
        except EventError as exc:
            raise RunInputError("type", str(exc), sorted(EVENTS)) from exc

    # ------------------------------------------------------------- interface

    @property
    def finished(self) -> bool:
        return self.cycle >= self.horizon

    def inject(
        self, type_: str, target: str, params: dict[str, Any] | None = None, cause: str = "intentional"
    ) -> dict[str, Any]:
        """Queue a user event for the next cycle (the frontend's "select a node and trigger")."""
        if self.finished:
            raise RunFinishedError("la corrida terminó")
        req = EventRequest(type_, target, tuple((params or {}).items()), "user", cause)
        resolved, area = self._check_event(req)
        self.queue.append(req)
        rec = {"cycle": self.cycle, **req.as_dict()}
        self.injected.append(rec)
        self.log.append(self.cycle, "inject", "user", "event_queued", rec)
        return {
            "accepted": True,
            "applies_at_cycle": self.cycle,
            "resolved_target": resolved,
            "area": area,
            "notice": NOTICE if cause == "intentional" else None,
        }

    def submit_action(
        self,
        action: str,
        target: str,
        role: str,
        params: dict[str, Any] | None = None,
        agent: str | None = None,
    ) -> dict[str, Any]:
        """Queue a course of action from an external agent for the next cycle. Only its structure is
        checked here; the cycle validates it like any staff proposal and spends attention, resources
        and crews to execute it."""
        if self.finished:
            raise RunFinishedError("la corrida terminó")
        spec = ACTIONS.get(action)
        if spec is None:
            raise RunInputError("action", "acción desconocida", sorted(ACTIONS))
        roles = sorted(r.value for r in spec.proposers)
        if role not in roles:
            raise RunInputError("role", f"el rol no puede proponer {action}", roles)
        net = self.network
        if action == "restore_element":
            known = target in net.areas or target in net.corridors
        elif spec.target == "area":
            known = target in net.areas
        elif spec.target == "corridor":
            known = target in net.corridors
        else:
            known = target in self.defense_areas
        if not known:
            raise RunInputError("target", f"{target}: objetivo desconocido para {action}", not_found=True)
        self.action_queue.append(
            COA(action, target, role, "external_agent", params=tuple((params or {}).items()))
        )
        rec = {
            "cycle": self.cycle,
            "action": action,
            "target": target,
            "role": role,
            "params": dict(params or {}),
            "agent": agent,
            "after_events": len(self.injected),  # keeps the input order when the run is rebuilt
        }
        self.actions.append(rec)
        self.log.append(self.cycle, "inject", "external", "action_queued", rec)
        return {
            "accepted": True,
            "applies_at_cycle": self.cycle,
            "action": action,
            "target": target,
            "role": role,
            "notice": NOTICE,
        }

    def step(self, n: int = 1) -> list[dict[str, Any]]:
        out = []
        for _ in range(n):
            if self.finished:
                break
            out.append(self._cycle())
        return out

    def run_to_end(self) -> None:
        while not self.finished:
            self._cycle()

    # ---------------------------------------------------------------- views

    def _real_snapshot(self) -> dict[str, tuple[float, bool]]:
        g = self.real.grid
        return {a: (g.served_mw[a], a not in g.blackout_areas) for a in self.network.order}

    def _view(self, role: str, obs: ObservedState, reports: tuple, **extra: Any) -> AgentView:
        h = self.cfg.clock["history"]
        return AgentView(
            role=role,
            cycle=self.cycle,
            observed=obs,
            history=tuple(self.observations[-h - 1 : -1]),
            mission=self.mission,
            policy=self.policy,
            resources=tuple((p, round(self.ledger.available(p), 3)) for p in self.ledger.capacity),
            field_reports=reports,
            feedback=tuple(self.feedback),
            active=tuple(sorted(self.ex.active)),
            crew_eta=self._crew_eta(),
            **extra,
        )

    def _adversary_view(self) -> AdversaryView:
        real = self.real
        g = real.grid
        demand = sum(g.load_mw.values())
        return AdversaryView(
            cycle=self.cycle,
            budget_left=(self.adversary.budget - self.adversary.spent) if self.adversary else 0.0,
            posture=tuple(
                (a, "segmented" if d.segmented else ("manual" if d.manual_ops else "normal"))
                for a, d in real.digital.items()
            ),
            my_effects=tuple(
                (e.id, e.event, e.area or e.target, e.established, e.start, e.cleared)
                for e in real.effects
                if e.source == "adversary"
            ),
            public_served_share=sum(g.served_mw.values()) / demand if demand else 1.0,
            public_dark_areas=tuple(sorted(g.blackout_areas)),
        )

    def _people(self) -> float:
        return self.real.grid.people_without_power()

    def _sites(self, target: str) -> list[str]:
        """Areas where a crew can carry out an action on `target`."""
        net = self.network
        if target in net.areas:
            return [target]
        if target in net.corridors:
            return [net.corridors[target].a, net.corridors[target].b]
        return self.defense_areas.get(target) or list(net.order)

    def _crews_view(self) -> list[dict[str, Any]]:
        """Crews with the map position of their area's anchor substation (mapa 3 bus id and lon/lat)."""
        if not self.roster:
            return []
        out = []
        buses = self.network.buses
        for c in self.roster.snapshot():
            anchor = self.network.areas[c["position"]].anchor_bus
            target = c["target"] if c["target"] in self.network.areas else None
            out.append(
                {
                    **c,
                    "bus": bus_id(anchor) if anchor is not None else None,
                    "lon": buses.lon[anchor] if anchor is not None else None,
                    "lat": buses.lat[anchor] if anchor is not None else None,
                    "target_bus": bus_id(cast(int, self.network.areas[target].anchor_bus))
                    if target
                    else None,
                }
            )
        return out

    def _crew_eta(self) -> tuple[tuple[str, int], ...]:
        if not self.roster:
            return ()
        etas = ((a, self.roster.best_eta(a)) for a in self.network.order)
        return tuple((a, e) for a, e in etas if e is not None)

    def _admissible(self, reqs: list[EventRequest]) -> list[EventRequest]:
        """Adversary events that resolve to an area, zone or defence function. Anything else is
        dropped and logged, so a bad request never stops the run (cyber.md 8 item 7)."""
        out = []
        for r in reqs:
            try:
                resolved, _ = self.executor.resolve(r)
            except EventError as exc:
                self.log.append(
                    self.cycle,
                    "events",
                    "engine",
                    "adversary_event_rejected",
                    {**r.as_dict(), "reason": str(exc)},
                )
                continue
            if (
                resolved in self.network.areas
                or resolved in self.network.zones
                or resolved in self.defense_areas
            ):
                out.append(r)
            else:
                self.log.append(
                    self.cycle,
                    "events",
                    "engine",
                    "adversary_event_rejected",
                    {**r.as_dict(), "reason": "not_abstract"},
                )
        return out

    # ---------------------------------------------------------------- cycle

    def _cycle(self) -> dict[str, Any]:
        """Run one decision cycle and return its snapshot. The steps are ordered because each reads what the
        previous one wrote.

        0. Let the executor advance the actions already in force and free the resources it releases.
        1. Events: the ones scheduled for this cycle, the queued injections, background failures (stochastic
           runs only, from cycle 1) and the adversary's. They hit the real state before anything is observed, so
           the cycle sees its own events.
        2. Observe: agents never read the real state. `observe` builds what the digital layer lets through
           (delay, bias, false alarms) from the real history.
        3. ISR builds the picture, C2 sets the intent, and the staff (operations, stabilization, logistics)
           propose courses of action (COA). Duplicates by key keep the highest benefit.
        4. Validate every COA against the real state and the resources, collect the vetoes of stabilization and
           logistics, and let C2 decide (with an LLM pick when one is configured). Actions queued by an external
           agent are approved too, unless C2 already approved the same key.
        5. Execute the approved COAs one by one. Each approval spends operator attention and is validated again,
           because earlier actions of this cycle change the state. A failed validation, a stochastic action
           failure or a missing crew becomes `ActionFeedback`, not an exception.
        6. Evaluate, audit, let the adversary learn, write the audit log, build the snapshot and advance
           `self.cycle`."""
        k, real, net = self.cycle, self.real, self.network
        real.cycle = k
        self.ledger.new_cycle(k)
        notes = self.executor.tick(real, self.ex)
        for key in self.ex.released:
            self.ledger.release(key)
        self.ex.released.clear()
        if self.roster:
            self.roster.sync(k, {r.action_key for r in self.ledger.reservations if r.pool == "field_crews"})

        # 1. events
        reqs = [*self.scheduled.get(k, []), *self.queue]
        self.queue = []
        if self.chance and k > 0:
            reqs += [
                EventRequest(e["type"], e["target"], tuple(e["params"].items()), "external", "failure")
                for e in self.chance.background(list(net.zones))
            ]
        if self.adversary:
            reqs += self._admissible(self.adversary.act(self._adversary_view()))
        applied = []
        if reqs:
            pairs = []
            for r in reqs:
                self.effect_seq += 1
                pairs.append((r, f"fx{self.effect_seq}"))
            for eff, status in self.executor.apply_events(real, pairs):
                applied.append(
                    {
                        "effect": eff.id,
                        "type": eff.event,
                        "target": eff.target,
                        "area": eff.area,
                        "source": eff.source,
                        "cause": eff.cause,
                        "status": status,
                    }
                )
        self.history_real.append(self._real_snapshot())

        # 2. observe
        prev = self.observations[-1] if self.observations else None
        obs, truth = observe(
            net,
            real,
            self.history_real,
            prev,
            self.rng_digital,
            self.config.uncertainty,
            self.cfg.digital,
            self.defense_areas,
        )
        self.observations.append(obs)
        reports = tuple(r for r in self.ex.pending_reports if r.cycle <= k)
        self.ex.pending_reports = [r for r in self.ex.pending_reports if r.cycle > k]

        # 3. understand, intent, plan
        isr_report, isr_coas = self.isr.step(self._view("isr", obs, reports))
        c2_view = self._view("c2", obs, reports, isr=isr_report)
        self.c2.observe(c2_view)
        intent = self.c2.intent(c2_view)
        staff = {
            r: self._view(r, obs, reports, isr=isr_report, intent=intent)
            for r in ("operations", "stabilization", "logistics")
        }
        coas = [
            *isr_coas,
            *self.ops.propose(staff["operations"]),
            *self.stab.propose(staff["stabilization"]),
            *self.logistics.propose(staff["logistics"]),
        ]
        unique: dict[str, COA] = {}
        for c in coas:
            if c.key not in unique or c.benefit > unique[c.key].benefit:
                unique[c.key] = c
        coas = list(unique.values())

        # 4. validate and decide
        ctx = ValidationContext(
            net,
            real,
            self.ledger,
            self.mission,
            intent,
            self.cfg.actions,
            self.defense_areas,
            active=set(self.ex.active),
        )
        verdicts = {c.key: validate(c, ctx) for c in coas}
        vetoes = {
            **self.stab.review(staff["stabilization"], coas),
            **self.logistics.review(staff["logistics"], coas),
        }
        c2_view = self._view("c2", obs, reports, isr=isr_report, intent=intent)
        decisions = self.c2.decide(c2_view, coas, verdicts, vetoes, self._llm_pick(c2_view))
        # external agent actions join C2's approvals unless C2 already approved the same one
        approved = {d.coa.key for d in decisions if d.approved}
        for coa in self.action_queue:
            if coa.key not in approved:
                decisions.append(Decision(coa, True, "external_agent", validate(coa, ctx)))
                approved.add(coa.key)
        self.action_queue = []

        # 5. execute
        executed, feedback, wrong, ok_count = [], [], 0, 0
        for d in (d for d in decisions if d.approved):
            self.ledger.spend({"operator_attention": 1}, f"c2:{k}", None)
            v = validate(d.coa, ctx)
            if not v.ok:
                feedback.append(ActionFeedback(k, d.coa.action, d.coa.target, False, v.observable_code))
                executed.append({**d.coa.as_dict(), "verdict": v.code, "ok": False})
                continue
            if self.chance and not self.chance.action_succeeds(d.coa.action):
                # it did not work on this attempt: attention spent, durable resources kept
                feedback.append(ActionFeedback(k, d.coa.action, d.coa.target, False, "action_failed"))
                executed.append({**d.coa.as_dict(), "verdict": "failed", "ok": False})
                continue
            if wrong_decision(real, d.coa):
                wrong += 1
            duration = self.cfg.actions.get(d.coa.action, {}).get("duration")
            if d.coa.action == "restore_element":
                duration = None  # the executor releases the crew when the repair ends
            arrival, crew = None, None
            if self.roster and d.coa.action in self.crew_actions:
                work = int(duration) if duration else None
                job = self.roster.dispatch(self._sites(d.coa.target), d.coa.key, k, work)
                if job is None:  # every crew in range was taken earlier in this cycle
                    feedback.append(ActionFeedback(k, d.coa.action, d.coa.target, False, "no_crew_in_range"))
                    executed.append({**d.coa.as_dict(), "verdict": "no_crew_in_range", "ok": False})
                    continue
                arrival, crew = job.arrival, job.crew
            start = arrival if arrival is not None else k
            self.ledger.spend(
                costs_of(d.coa, self.cfg.actions), d.coa.key, start + int(duration) if duration else None
            )
            self.executor.apply_action(real, self.ex, d.coa, arrival)
            ctx.active = set(self.ex.active)
            ok_count += 1
            feedback.append(ActionFeedback(k, d.coa.action, d.coa.target, True, "executed"))
            executed.append(
                {
                    **d.coa.as_dict(),
                    "verdict": "ok",
                    "ok": True,
                    **({"crew": crew, "arrival": arrival} if crew else {}),
                }
            )
        self.feedback = feedback

        # 6. evaluate and adapt
        eval_ctx = ValidationContext(
            net,
            real,
            self.ledger,
            self.mission,
            None,
            self.cfg.actions,
            self.defense_areas,
            active=set(self.ex.active),
            check_physics=False,
        )
        metrics = self.evaluator.record(
            real,
            isr_report,
            self.c2.estimate,
            eval_ctx,
            len(coas),
            sum(d.approved for d in decisions),
            ok_count,
            wrong,
            self._people(),
        )
        affected = sorted(real_affected(real))
        findings = self.auditor.audit(
            CycleRecord(
                k,
                tuple(d.as_dict() for d in decisions),
                tuple(executed),
                tuple(affected),
                isr_report.affected,
            )
        )
        if self.adversary:
            self.adversary.learn(self._adversary_view())

        decisions_out = [d.as_dict() for d in decisions]
        self.log.append(
            k,
            "events",
            "engine",
            "events_applied",
            {"events": applied, "transient": real.last_transient if applied else None},
        )
        self.log.append(
            k,
            "observe",
            "digital",
            "observation",
            {"alarms": len(obs.alarms), "false_alarms": len(truth.false_alarms)},
        )
        self.log.append(k, "understand", "isr", "picture", isr_report.as_dict())
        self.log.append(k, "intent", "c2", "intent", intent.as_dict())
        self.log.append(k, "plan", "staff", "proposals", {"coas": [c.as_dict() for c in coas]})
        self.log.append(k, "decide", "c2", "decisions", {"decisions": decisions_out, "vetoes": vetoes})
        self.log.append(k, "execute", "engine", "executed", {"executed": executed, "notes": notes})
        self.log.append(k, "evaluate", "auditor", "findings", {"findings": findings})
        self.log.append(k, "evaluate", "evaluator", "metrics", metrics.as_dict())

        snapshot = self._snapshot(
            k, applied, obs, isr_report, intent, coas, decisions, executed, notes, findings, metrics.as_dict()
        )
        self.snapshots.append(snapshot)
        self.cycle += 1
        return snapshot

    def _snapshot(
        self,
        k: int,
        applied: list,
        obs: ObservedState,
        isr_report,
        intent,
        coas: list[COA],
        decisions: list[Decision],
        executed: list,
        notes: list,
        findings: list,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        real, net = self.real, self.network
        g = real.grid
        areas = {}
        for a in net.order:
            d = real.digital[a]
            areas[a] = {
                "demand_mw": round(g.load_mw[a], 1),
                "served_mw": round(g.served_mw[a], 1),
                "energized": a not in g.blackout_areas,
                "digital": {
                    "telemetry": round(d.telemetry, 2),
                    "delay": d.delay,
                    "reliable": d.reliable,
                    "comms": d.comms,
                    "remote_control": d.remote_control,
                    "segmented": d.segmented,
                    "manual_ops": d.manual_ops,
                    "external_ok": d.external_ok,
                },
                "effects": [e.id for e in real.active_effects(a)],
            }
        return {
            "cycle": k,
            "t_min": k * self.cfg.clock["cycle_minutes"],
            "events": applied,
            "real": {
                "areas": areas,
                "corridors": {cid: ("closed" if g.corridor_closed(cid) else "open") for cid in net.corridors},
                "disabled_defenses": sorted(g.disabled_defenses),
                "transient": real.last_transient
                if real.last_transient and real.last_transient["cycle"] == k
                else None,
                "worst_level": real.worst_level,
            },
            "grid": None if self.light else g.frame(),
            "transient": real.last_timeline
            if real.last_transient and real.last_transient["cycle"] == k
            else None,
            "areas": {
                a: {
                    "observability": real.digital[a].health(),
                    "posture": "segmented"
                    if real.digital[a].segmented
                    else ("manual" if real.digital[a].manual_ops else "normal"),
                    "effects": [
                        {"id": e.id, "type": e.event, "source": e.source} for e in real.active_effects(a)
                    ],
                }
                for a in net.order
            },
            "observed": obs.as_dict(),
            "estimated": {
                "isr": isr_report.as_dict(),
                "c2": {
                    "intent": intent.as_dict(),
                    "served_estimate": {a: round(v, 1) for a, v in self.c2.estimate.items()},
                },
                "stabilization": {"waiting_for_stability": k <= self.stab.unstable_until},
            },
            "proposals": [c.as_dict() for c in coas],
            "decisions": [d.as_dict() for d in decisions],
            "executed": executed,
            "notes": notes,
            "findings": findings,
            "resources": self.ledger.snapshot(),
            "crews": self._crews_view(),
            "llm": self.llm_note,
            "metrics": metrics,
        }

    # ------------------------------------------------------------ outputs

    def _llm_pick(self, view: AgentView):
        """C2's LLM advisor for this cycle, or None. A recorded pick (replay) wins over a new call,
        so a replay never calls the LLM again. The advisor sees only C2's view, never the real state."""
        if not self.config.llm_commander:
            self.llm_note = None
            return None
        recorded = dict(self.config.llm_choices)
        k = self.cycle
        model = getattr(self.advisor, "model", None)
        # what the operation view shows about C2's LLM this cycle (replaced below when it is called)
        self.llm_note = {"status": "idle" if self.advisor or k in recorded else "unavailable", "model": model}

        def pick(eligible: list[COA], capacity: int) -> set[str] | None:
            if k in recorded:
                self.llm_note = {
                    "status": "replayed",
                    "model": model,
                    "chosen": list(recorded[k]),
                    "options": len(eligible),
                }
                return set(recorded[k])
            if self.advisor is None:
                return None
            options = [{"id": c.key, **c.as_dict()} for c in eligible]
            context = {
                "cycle": k,
                "minutes": k * self.cfg.clock["cycle_minutes"],
                "mission": {"priority_areas": list(view.mission.priority_areas)},
                "policy": view.policy.id,
                "intent": view.intent.as_dict() if view.intent else None,
                "isr": view.isr.as_dict() if view.isr else None,
                "outages_seen": view.outages(),
                "alarms": [{"area": a.area, "kind": a.kind} for a in view.observed.alarms],
                "resources": dict(view.resources),
                "crew_eta_cycles": dict(view.crew_eta),
            }
            answer = self.advisor.choose(context, options, capacity)
            chosen = (answer or {}).get("chosen")
            if not isinstance(chosen, list):
                self.log.append(k, "decide", "c2", "llm_unavailable", {})
                self.llm_note = {"status": "unavailable", "model": model, "options": len(options)}
                return None
            keys = tuple(str(x) for x in chosen if str(x) in {o["id"] for o in options})[:capacity]
            self.llm_record[k] = keys
            assert answer is not None  # `chosen` came from it
            explanation = str(answer.get("explanation", ""))[:2000]
            self.log.append(
                k, "decide", "c2", "llm_choice", {"chosen": list(keys), "explanation": explanation}
            )
            self.llm_note = {
                "status": "chosen",
                "model": model,
                "chosen": list(keys),
                "explanation": explanation,
                "options": len(options),
                "capacity": capacity,
            }
            return set(keys)

        return pick

    def recipe(self) -> dict[str, Any]:
        return {
            "config": self.config.as_dict(),
            "injected": list(self.injected),
            "llm_choices": [[k, list(v)] for k, v in sorted(self.llm_record.items())],
            "cycle": self.cycle,
            "actions": list(self.actions),
        }

    def trace(self) -> dict[str, Any]:
        return {
            "head": self.log.head,
            "verified": self.log.verify(),
            "entries": self.log.entries,
            "recipe": self.recipe(),
        }

    def report(self) -> dict[str, Any]:
        ind = self.evaluator.report(
            self.mission.continuity_threshold, self.mission.observability_threshold, self.real.worst_level
        )
        consequence = ind.pop("consequence", {})
        moments = []
        if self.evaluator.onset is not None:
            moments.append({"cycle": self.evaluator.onset, "rationale_key": "aar_onset"})
        if self.evaluator.understood_at is not None:
            moments.append({"cycle": self.evaluator.understood_at, "rationale_key": "aar_understood"})
        first = next((s["cycle"] for s in self.snapshots if s["executed"]), None)
        if first is not None:
            moments.append({"cycle": first, "rationale_key": "aar_first_action"})
        rec = ind.get("recoverability_cycles")
        if rec is not None and self.evaluator.onset is not None:
            moments.append({"cycle": self.evaluator.onset + rec, "rationale_key": "aar_recovered"})
        out = {
            "run": {
                "template": self.template.id,
                "question_key": self.template.question_key,
                "policy": self.policy.id,
                "seed": self.config.seed,
                "uncertainty": self.config.uncertainty,
                "horizon": self.horizon,
                "cycles_run": self.cycle,
                "finished": self.finished,
                "operating_point": self.operating_point,
                "defenses": self.defenses_id,
            },
            "notice": NOTICE,
            "mission": {
                "id": self.mission.id,
                "label_key": self.mission.label_key,
                "priority_areas": list(self.mission.priority_areas),
                "continuity_threshold": self.mission.continuity_threshold,
            },
            "indicators": ind,
            "coordination": self.auditor.summary(),
            "consequence": consequence,
            "adversary": None
            if not self.adversary
            else {
                "objective": self.adversary.objective,
                "adaptive": self.adversary.adaptive,
                "budget": self.adversary.budget,
                "spent": self.adversary.spent,
                "strategy_mix": self.adversary.strategy_mix(),
            },
            "after_action": sorted(moments, key=lambda m: cast(int, m["cycle"])),
            "trace_head": self.log.head,
        }
        inc = self.cfg.incidents.get(self.template.id)
        if inc:
            out["incident"] = {
                **incident_public(
                    inc,
                    len(self.template.scenario_events),
                    self.horizon,
                    self.operating_point,
                ),
                "consequence_card": incident_card(
                    inc,
                    self.evaluator.series,
                    self.real.worst_level,
                    [s["transient"]["summary"] for s in self.snapshots if s.get("transient")],
                ),
            }
        return out
