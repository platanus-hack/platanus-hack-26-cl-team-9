"""Adaptive adversary (docs/strategy.md 5.1, cyber.md section 8 item 7).

It pursues one abstract objective with a limited budget, using only the abstract event catalog at
operating-area, zone or defence-function level (never a substation, corridor or line). It sees only what the defence exposes. The adaptive variant learns with EXP3
(seeded multiplicative weights) and shifts strategy when the defence changes; the static variant
plays the template's plan. Its weights stay internal: no output ranks areas or elements.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from cascadasen.domain.agents.base import AdversaryView
from cascadasen.domain.theater.catalog import EVENTS, Role
from cascadasen.domain.theater.execution import EventRequest

NON_PHYSICAL = {"D3_unreliable_data", "D5_false_alarms"}
TARGET_KINDS = ("area", "zone", "defense")  # the only target kinds the adversary may use


def arms_for(events: list[str], targets: dict[str, list[str]]) -> list[tuple[str, str]]:
    """(event, target) arms: each event over the first abstract target kind it accepts."""
    arms = []
    for ev in events:
        kind = next((k for k in TARGET_KINDS if k in EVENTS[ev].targets and targets.get(k)), None)
        arms += [(ev, t) for t in targets.get(kind, [])] if kind else []
    return arms


@dataclass
class Pending:
    arm: int
    cycle: int
    event: str
    target: str


@dataclass
class AdversaryAgent:
    targets: dict[str, list[str]]  # target kind -> ids (areas, zones, defence functions)
    objective: str
    budget: float
    adaptive: bool
    plan: list[dict]
    rng: random.Random
    catalog: dict
    role: Role = Role.ADVERSARY
    arms: list[tuple[str, str]] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    pending: list[Pending] = field(default_factory=list)
    next_opportunity: int = 0
    spent: float = 0.0
    chosen: list[tuple[int, str]] = field(default_factory=list)  # (cycle, event type): the visible strategy

    def __post_init__(self) -> None:
        events = self.catalog["objectives"][self.objective]
        self.arms = arms_for(list(events), self.targets)
        planned = {(p["type"], p["target"]) for p in self.plan}
        self.weights = [2.0 if arm in planned else 1.0 for arm in self.arms]

    def _cost(self, event: str) -> float:
        return float(self.catalog["costs"]["physical" if EVENTS[event].family == "physical" else "digital"])

    def _probs(self) -> list[float]:
        gamma, k = float(self.catalog["gamma"]), len(self.weights)
        total = sum(self.weights)
        return [(1 - gamma) * w / total + gamma / k for w in self.weights]

    def act(self, view: AdversaryView) -> list[EventRequest]:
        if self.budget - self.spent <= 0:
            return []
        if not self.adaptive:
            out = []
            for p in self.plan:
                if p["cycle"] == view.cycle and self.spent + self._cost(p["type"]) <= self.budget:
                    self.spent += self._cost(p["type"])
                    self.chosen.append((view.cycle, p["type"]))
                    out.append(
                        EventRequest(
                            p["type"],
                            p["target"],
                            tuple((p.get("params") or {}).items()),
                            "adversary",
                            "intentional",
                        )
                    )
            return out
        if view.cycle < self.next_opportunity or view.cycle == 0:
            return []
        probs = self._probs()
        r, acc, arm = self.rng.random(), 0.0, len(probs) - 1
        for i, prob in enumerate(probs):
            acc += prob
            if r <= acc:
                arm = i
                break
        event, target = self.arms[arm]
        if self.spent + self._cost(event) > self.budget:
            return []
        self.spent += self._cost(event)
        self.next_opportunity = view.cycle + int(self.catalog["cooldown"])
        self.pending.append(Pending(arm, view.cycle, event, target))
        self.chosen.append((view.cycle, event))
        return [EventRequest(event, target, (), "adversary", "intentional")]

    def _reward(self, p: Pending, view: AdversaryView) -> float | None:
        mine = [e for e in view.my_effects if e[1] == p.event and e[2] == p.target and e[4] == p.cycle]
        if not mine or view.cycle - p.cycle < 2:
            return None
        _, _, area, established, start, cleared = mine[0]
        if not established:
            return 0.0
        posture = dict(view.posture).get(area, "normal")
        persisted = cleared is None or cleared - start >= 2
        if self.objective in ("reduce_observability", "raise_uncertainty"):
            return 1.0 if persisted else 0.3
        if self.objective == "pressure_resources":
            return 1.0 if posture != "normal" else 0.3
        if self.objective == "provoke_unnecessary_actions":
            return 1.0 if posture != "normal" and p.event in NON_PHYSICAL else 0.2
        # complicate_recovery: rewarded by delayed recovery (the effect outlived the defence's
        # response, or the area is still dark), never by megawatts or people (cyber.md 8 item 7)
        return 1.0 if persisted or area in view.public_dark_areas else 0.3

    def learn(self, view: AdversaryView) -> None:
        if not self.adaptive:
            return
        gamma, k = float(self.catalog["gamma"]), len(self.weights)
        probs = self._probs()
        for p in list(self.pending):
            r = self._reward(p, view)
            if r is None:
                continue
            self.pending.remove(p)
            self.weights[p.arm] *= math.exp(gamma * (r / probs[p.arm]) / k)
        top = max(self.weights)
        self.weights = [w / top for w in self.weights]  # keep numbers bounded

    def strategy_mix(self) -> dict[str, int]:
        """Event types chosen so far (no areas: the visible strategy, never a target ranking)."""
        mix: dict[str, int] = {}
        for _, ev in self.chosen:
            mix[ev] = mix.get(ev, 0) + 1
        return mix
