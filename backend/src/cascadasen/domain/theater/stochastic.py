"""Chance in the theatre: the world does not behave exactly as planned (docs/strategy.md section 4).

Each source draws from its own seeded stream (`theater/rng.py`), so a policy change never alters
the luck of the world:

    physics   size of abstract events, defence schemes that fail to act in a transient
    external  unplanned external events (demand surges, renewable drops) during the run
    ops       whether an approved action works on the first attempt, repair speed
    field     what a field crew misses on site

Explicit sizes given by a scenario or a user are kept exact; only catalog defaults are sampled.
All parameters live in `theater.yaml` under `stochastic` and are declared assumptions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from cascadasen.domain.theater.rng import rng_for

STREAMS = ("physics", "external", "ops", "field")


@dataclass
class Chance:
    params: dict[str, Any]
    physics: random.Random
    external: random.Random
    ops: random.Random
    field: random.Random

    @classmethod
    def for_run(cls, seed: int, params: dict[str, Any]) -> Chance:
        return cls(params, *(rng_for(seed, name) for name in STREAMS))

    # ------------------------------------------------------------- events

    def effect_params(self, defaults: dict[str, Any], explicit: dict[str, Any]) -> dict[str, Any]:
        """Catalog defaults with a sampled size; explicit values pass through unchanged."""
        out = dict(defaults)
        if "share" in out and "share" not in explicit:
            out["share"] = round(self._beta(float(out["share"]), self.physics), 4)
        if "mw" in out and "mw" not in explicit:
            out["mw"] = round(
                self._lognormal(float(out["mw"]), self.params["effect_mw_sigma"], self.physics), 1
            )
        out.update(explicit)
        return out

    @staticmethod
    def _lognormal(median: float, sigma: float, rng: random.Random) -> float:
        return median * math.exp(rng.gauss(0.0, sigma)) if median > 0 else median

    def misoperating(self, defence_ids: list[str]) -> list[str]:
        """Defence functions that fail to act in this transient."""
        p = float(self.params["defense_misoperation_p"])
        return [d for d in defence_ids if self.physics.random() < p]

    def background(self, zones: list[str]) -> list[dict[str, Any]]:
        """Unplanned external events this cycle: at most one, at zone level."""
        if not zones or self.external.random() >= float(self.params["background_event_p"]):
            return []
        menu = self.params["background_events"]
        kinds = sorted(menu)
        kind = self.external.choices(kinds, weights=[float(menu[k]["weight"]) for k in kinds])[0]
        spec = {k: v for k, v in menu[kind].items() if k != "weight"}
        if "share" in spec:
            spec["share"] = round(self._beta(float(spec["share"]), self.external), 4)
        return [{"type": kind, "target": self.external.choice(zones), "params": spec}]

    def _beta(self, mean: float, rng: random.Random) -> float:
        if mean <= 0 or mean >= 1:
            return mean
        k = float(self.params["effect_share_concentration"])
        return min(0.999, max(0.001, rng.betavariate(mean * k, (1 - mean) * k)))

    # ------------------------------------------------------------ actions

    def action_succeeds(self, action: str) -> bool:
        p = float(self.params["action_success_p"].get(action, 1.0))
        return p >= 1.0 or self.ops.random() < p

    def repair_cycles(self, nominal: int) -> int:
        return max(1, round(self._lognormal(float(nominal), float(self.params["repair_sigma"]), self.ops)))

    def restore_factor(self) -> float:
        return min(2.0, self._lognormal(1.0, float(self.params["restore_share_sigma"]), self.ops))

    def field_misses(self) -> bool:
        return self.field.random() < float(self.params["field_miss_p"])
