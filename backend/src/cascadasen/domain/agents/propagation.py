"""Propagating cyberattack (docs/attack-sim.md section 3.2, cyber.md section 8 item 7).

Why: the "Ciberataque" scenario asks how far an intrusion that moves from one operating area to its
neighbours gets before the defence contains it, and what the grid loses on the way. It models effects
only, at operating-area level, with the abstract catalog:

- an area becomes **compromised**: the intrusion is latent there, nothing is visible yet;
- `strike_delay` cycles later it **strikes**: supervision loses communications (D4), remote dispatch is
  lost (C5) and a share of the area's generation trips (C1). The cascade engine decides what that does
  to the grid. Why latent: a defence that saw the intrusion at once would contain it before it moved;
- every `spread_cooldown` cycles a compromised area tries each neighbouring area (a shared corridor)
  with probability `spread_p`. A segmented area (the defence's `digital_segmentation`) stops the jump
  with probability `isolation_p`, whether it is the source or the target;
- the intrusion is cleaned up when the defence keeps the area segmented for `clean_after_segmented`
  cycles, or clears every effect there (restoration by field crews). It is then eradicated with
  probability `eradicate_p`; otherwise it strikes again. An eradicated area stays clean. The damage
  (comms, generation) stays until crews restore the area.

It does not learn, has no objective and never ranks areas: the start is a seeded random area with at
least `min_neighbours` neighbours, and spread is a coin per neighbour. It sees only the defence's
visible posture and its own effects (`AdversaryView`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.agents.base import AdversaryView
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.execution import EventRequest

# name: (min, max) of every parameter a request may override
BOUNDS: dict[str, tuple[float, float]] = {
    "strike_delay": (0, 12),
    "spread_cooldown": (1, 12),
    "spread_p": (0.0, 1.0),
    "isolation_p": (0.0, 1.0),
    "eradicate_p": (0.0, 1.0),
    "generation_share": (0.0, 1.0),
    "attack_win_lost_share": (0.1, 1.0),
    "min_neighbours": (1, 6),
    "clean_after_segmented": (1, 12),
    "crew_max_eta_cycles": (1, 72),
    "recovered_lost_share": (0.0, 0.5),
}
STATES = ("clean", "compromised", "struck", "eradicated")


class PropagationParamError(ValueError):
    def __init__(self, name: str, message: str) -> None:
        super().__init__(message)
        self.name = name


def propagation_params(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, float]:
    """Defaults from `theater.yaml` → `cyber_attack` with the request's overrides, bounds checked."""
    out = {k: float(v) for k, v in defaults.items()}
    for k, v in (overrides or {}).items():
        if k not in BOUNDS:
            raise PropagationParamError(k, f"parámetro desconocido; válidos: {', '.join(sorted(BOUNDS))}")
        lo, hi = BOUNDS[k]
        if not isinstance(v, int | float) or not lo <= float(v) <= hi:
            raise PropagationParamError(k, f"entre {lo:g} y {hi:g}")
        out[k] = float(v)
    return out


@dataclass
class _Area:
    state: str = "clean"
    since: int = 0  # cycle it entered the state
    next_try: int = 0  # next cycle it may spread
    walled: int = 0  # consecutive cycles the defence kept it segmented


@dataclass
class PropagatingAdversary:
    neighbours: dict[str, list[str]]  # area -> areas sharing a corridor (public topology)
    params: dict[str, float]
    rng: random.Random
    role: Role = Role.ADVERSARY
    objective: str = "propagation"
    adaptive: bool = False
    budget: float = 0.0
    spent: float = 0.0
    areas: dict[str, _Area] = field(default_factory=dict)
    start: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)  # (cycle, kind, area): the visible story
    chosen: list[tuple[int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.areas = {a: _Area() for a in self.neighbours}

    # -- the interface the cycle uses (same as AdversaryAgent) --------------------------------------
    def act(self, view: AdversaryView) -> list[EventRequest]:
        if self.start is None:
            return self._seed(view.cycle)
        posture = dict(view.posture)
        out = self._strikes(view.cycle)
        self._spread(view.cycle, posture)  # silent: a jump only shows when that area strikes
        return out

    def learn(self, view: AdversaryView) -> None:
        """Clean-up: an area segmented long enough, or with every effect cleared, is eradicated with
        `eradicate_p`; a failed clean-up lets the intrusion strike again."""
        posture = dict(view.posture)
        for area, st in self.areas.items():
            if st.state not in ("compromised", "struck"):
                continue
            st.walled = st.walled + 1 if posture.get(area) == "segmented" else 0
            mine = [e for e in view.my_effects if e[2] == area and e[4] >= st.since and e[3]]
            cleared = bool(mine) and all(e[5] is not None for e in mine)
            if not cleared and st.walled < int(self.params["clean_after_segmented"]):
                continue
            st.walled = 0
            if self.rng.random() < self.params["eradicate_p"]:
                self._move(area, "eradicated", view.cycle)
            else:
                self.events.append({"cycle": view.cycle, "kind": "cleanup_failed", "area": area})
                if cleared:  # nothing left there: it strikes again now
                    self._move(area, "compromised", view.cycle)
                    st.since = view.cycle - int(self.params["strike_delay"])

    def strategy_mix(self) -> dict[str, int]:
        mix: dict[str, int] = {}
        for _, ev in self.chosen:
            mix[ev] = mix.get(ev, 0) + 1
        return mix

    # -- state ------------------------------------------------------------------------------------
    @property
    def started(self) -> bool:
        return self.start is not None

    def active(self) -> list[str]:
        return [a for a, st in self.areas.items() if st.state in ("compromised", "struck")]

    def snapshot(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "areas": {a: st.state for a, st in self.areas.items()},
            "counts": {s: sum(st.state == s for st in self.areas.values()) for s in STATES},
        }

    # -- mechanics ---------------------------------------------------------------------------------
    def _seed(self, cycle: int) -> list[EventRequest]:
        need = int(self.params["min_neighbours"])
        pool = sorted(a for a, n in self.neighbours.items() if len(n) >= need) or sorted(self.neighbours)
        self.start = self.rng.choice(pool)
        self._compromise(self.start, cycle)
        return []

    def _compromise(self, area: str, cycle: int) -> None:
        self._move(area, "compromised", cycle)
        self.areas[area].next_try = cycle + int(self.params["spread_cooldown"])

    def _strikes(self, cycle: int) -> list[EventRequest]:
        out = []
        for area, st in self.areas.items():
            if st.state == "compromised" and cycle - st.since >= int(self.params["strike_delay"]):
                self._move(area, "struck", cycle)
                out.append(self._event("D4_comms_loss", area, cycle))
                out.append(self._event("C5_remote_dispatch_loss", area, cycle))
                share = self.params["generation_share"]
                if share > 0:
                    out.append(self._event("C1_generation_loss", area, cycle, {"share": share}))
        return out

    def _spread(self, cycle: int, posture: dict[str, str]) -> None:
        for area in sorted(self.active()):
            st = self.areas[area]
            if cycle < st.next_try or st.since == cycle:
                continue
            st.next_try = cycle + int(self.params["spread_cooldown"])
            for nb in self.neighbours[area]:
                if self.areas[nb].state != "clean" or self.rng.random() >= self.params["spread_p"]:
                    continue
                walled = posture.get(area) == "segmented" or posture.get(nb) == "segmented"
                if walled and self.rng.random() < self.params["isolation_p"]:
                    self.events.append({"cycle": cycle, "kind": "blocked", "from": area, "area": nb})
                    continue
                self._compromise(nb, cycle)
                self.events[-1]["from"] = area

    def _move(self, area: str, state: str, cycle: int) -> None:
        self.areas[area].state, self.areas[area].since = state, cycle
        self.events.append({"cycle": cycle, "kind": state, "area": area})

    def _event(self, kind: str, area: str, cycle: int, params: dict | None = None) -> EventRequest:
        self.spent += 1
        self.chosen.append((cycle, kind))
        return EventRequest(kind, area, tuple((params or {}).items()), "adversary", "intentional")
