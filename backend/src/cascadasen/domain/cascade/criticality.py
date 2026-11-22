"""How much depends on a substation: what dies without backup, and how much traffic its fall adds to the other lines.

Why: the number of lines at a substation is a poor proxy for its importance. A hub inside a mesh can fall and nothing
happens, while a substation with two lines on the north-south backbone can take a third of the country with it. So the
score is measured, not guessed: the substation is switched off (every line that ends at it opens) and the grid answers.

Per substation, three measures:
  - `isolated_mw`: demand of the buses that end up cut off from the main grid. Topology only: there is no other path.
  - `collateral_mw` / `collateral_people`: demand that the cascade leaves unserved at OTHER buses. It includes the
    isolated demand, and also what is lost because the backup paths exist but cannot carry the flow (lines trip) or
    because an island falls under 47.5 Hz. The substation's own demand is not counted: it dies by definition.
  - `extra_loading`: the largest increase of loading on a surviving line, as a fraction of its capacity (1.0 = a line
    receives 100 % of its capacity in new traffic). DC flow before the cascade, so it shows the stress that triggers it.

The score (0 to 1) is `min(1, max(collateral_share / SATURATION_SHARE, STRESS_WEIGHT * min(1, extra_loading)))`.
Only real losses reach 1; a substation whose fall only stresses lines tops out at STRESS_WEIGHT.

ASSUMPTIONS (not calibrated, no source): SATURATION_SHARE, STRESS_WEIGHT, STRESSED_MIN_INCREASE and the band limits.
"""

from __future__ import annotations

import numpy as np

from .engine import run_cascade_state
from .flow import dc_flow, find_islands
from .network import ReducedNetwork
from .scenario import OperatingPoint

SATURATION_SHARE = 0.25  # losing 25 % of the national demand outside the substation scores 1
STRESS_WEIGHT = 0.5  # stress alone cannot score above this
STRESSED_MIN_INCREASE = (
    0.10  # a line counts as stressed if it ends above 100 % and gained 10 points of capacity
)
BANDS = [
    (0.66, "alta"),
    (0.33, "media"),
    (0.05, "baja"),
]  # score at or above -> band; below the last -> "ninguna"


def score_of(collateral_share: float, extra_loading: float) -> float:
    return min(
        1.0, max(collateral_share / SATURATION_SHARE, STRESS_WEIGHT * min(1.0, max(extra_loading, 0.0)))
    )


def band_of(score: float) -> str:
    return next((name for floor, name in BANDS if score >= floor), "ninguna")


def criticality_workflow(
    net: ReducedNetwork, point: OperatingPoint, open_lines: frozenset[str] = frozenset()
) -> dict[int, dict]:
    """Bus index -> measures and score, for every bus that still has a line in service. `open_lines` are already out
    (the user's cuts and what their cascade opened), so the score is that of the grid as it stands."""
    injection = point.gen - point.load
    base = dc_flow(net, set(open_lines), injection, find_islands(net, set(open_lines)))
    capacity = np.array([ln.capacity_mw for ln in net.lines])
    total_load = float(point.load.sum()) or 1.0
    out: dict[int, dict] = {}
    for bus in range(net.size):
        lines = sorted(ln.id for ln in net.lines if bus in (ln.a, ln.b) and ln.id not in open_lines)
        if not lines:
            continue
        out[bus] = _one_substation(net, point, bus, lines, base, capacity, injection, total_load, open_lines)
    return out


def _one_substation(net, point, bus, lines, base, capacity, injection, total_load, open_lines) -> dict:
    out = set(lines) | set(open_lines)
    islands = find_islands(net, out)
    # only the island the bus was in counts: islands left by earlier cuts are not this substation's doing
    home = set(next(i for i in find_islands(net, set(open_lines)) if bus in i))
    others = [isl for isl in islands if isl != [bus] and home.issuperset(isl)]
    main = max(others, key=len) if others else []
    isolated_mw = float(sum(point.load[b] for isl in others if isl is not main for b in isl))
    _, state = run_cascade_state(net, point, lines, open_lines=frozenset(open_lines))
    lost = point.load - state.load
    collateral_mw = float(lost.sum() - lost[bus])
    ratio = np.divide(state.load, point.load, out=np.ones(net.size), where=point.load > 0)
    people_lost = point.people * (1.0 - ratio)
    collateral_people = float(people_lost.sum() - people_lost[bus])
    after = dc_flow(net, out, injection, islands)
    keep = np.array([bus not in (ln.a, ln.b) for ln in net.lines])
    increase = np.where(keep, (np.abs(after) - np.abs(base)) / capacity, 0.0)
    loading = np.abs(after) / capacity
    share = collateral_mw / total_load
    extra = float(max(increase.max(), 0.0))
    score = score_of(share, extra)
    return {
        "degree": len(lines),
        "articulation": len(others) > 1,  # without it the rest of the grid falls apart: no backup path at all
        "own_load_mw": round(float(point.load[bus]), 1),
        "isolated_mw": round(isolated_mw, 1),
        "collateral_mw": round(collateral_mw, 1),
        "collateral_share": round(share, 4),
        "collateral_people": round(collateral_people),
        "extra_loading": round(extra, 3),
        "lines_stressed": int(((loading > 1.0) & (increase >= STRESSED_MIN_INCREASE) & keep).sum()),
        "criticality": round(score, 3),
        "band": band_of(score),
    }
