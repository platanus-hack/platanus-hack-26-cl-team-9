"""Build the `timeline.json` contract (docs/stack.md section 6 and 6.1) from a transient result."""

from __future__ import annotations

from bisect import bisect_right
from typing import Any

from cascadasen.domain.simulation.engine import TransientResult
from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.simulation.network import ReducedNetwork
from cascadasen.domain.simulation.params import Provenance

NOTICE = "Escenario hipotético: se modela el efecto, no el ataque."


def _freq_at(samples: list[tuple[float, float]], t: float) -> float | None:
    if not samples:
        return None
    i = bisect_right([s[0] for s in samples], t + 1e-9) - 1
    return samples[max(0, i)][1]


def _frame(network: ReducedNetwork, res: TransientResult, t: float, times: dict[str, Any]) -> dict[str, Any]:
    pre = t <= 0.0
    blackout_at = times["blackout_at"]
    weak = dict(res.weak_links)
    edges: dict[str, Any] = {}
    for cid, c in network.corridors.items():
        eff_pre = res.pre_state.corridor(network, cid)
        if eff_pre is None:
            edges[cid] = {"flow_mw": 0.0, "status": "open"}
            continue
        if pre:
            f = res.pre_flows.get(cid, 0.0)
            edges[cid] = {"flow_mw": round(f, 1), "status": "overload" if abs(f) > eff_pre[1] else "ok"}
            continue
        dark = any(blackout_at.get(a) is not None and t >= blackout_at[a] for a in (c.a, c.b))
        if cid in res.initial_open or (cid in weak and t >= weak[cid]) or dark:
            edges[cid] = {"flow_mw": 0.0, "status": "open"}
        elif cid in weak:
            edges[cid] = {"flow_mw": round(res.pre_flows.get(cid, 0.0), 1), "status": "overload"}
        else:
            f = res.post_flows.get(cid, res.pre_flows.get(cid, 0.0))
            eff = res.state.corridor(network, cid) or eff_pre
            edges[cid] = {"flow_mw": round(f, 1), "status": "overload" if abs(f) > eff[1] else "ok"}
    nodes = {}
    for a in network.order:
        was_dark = a in res.pre_state.blackout_areas
        bo = blackout_at.get(a)
        nodes[a] = {
            "energized": not was_dark and not (bo is not None and t >= bo),
            "island": res.island_of_area.get(a),
        }
    islands = {}
    for r in res.islands:
        bo = r.trace.blackout_t
        islands[r.id] = {"freq_hz": None if (bo is not None and t > bo) else _freq_at(r.trace.samples, t)}
    return {"t": round(t, 3), "edges": edges, "nodes": nodes, "islands": islands}


def build_timeline(
    network: ReducedNetwork,
    res: TransientResult,
    card: dict[str, Any],
    physics: Physics,
    *,
    scenario: str,
    defenses: str,
    behavior: str,
    failed_elements: list[str],
    provenance: list[Provenance],
    cause: dict[str, Any] | None = None,
    group_out: list[dict[str, Any]] | None = None,
    defenses_disabled: list[str] | None = None,
    frames: bool = True,
) -> dict[str, Any]:
    blackout_at = {}
    for r in res.islands:
        if r.result in ("blackout", "local_cut", "no_load"):
            for a in r.areas:
                blackout_at[a] = r.trace.blackout_t or 0.0
    times = {"blackout_at": blackout_at}
    out: dict[str, Any] = {
        "scenario": scenario,
        "defenses": defenses,
        "behavior": behavior,
        "failed_elements": failed_elements,
        "duration_s": physics.horizon,
        "truncated": res.truncated,
        "events": res.events,
        "frames": [],
        "summary": card,
        "provenance": list({p.key: p.as_dict() for p in provenance}.values()),
    }
    if frames:
        n = round(physics.horizon / physics.frame_step)
        grid = {round(k * physics.frame_step, 3) for k in range(n + 1)}
        grid |= {e["t"] for e in res.events if 0 <= e["t"] <= physics.horizon}
        out["frames"] = [_frame(network, res, t, times) for t in sorted(grid)]
    if cause:
        out["cause"] = cause
        if cause.get("kind") == "cyber_effect":
            out["notice"] = NOTICE
    if group_out:
        out["group_out"] = group_out
    if defenses_disabled:
        out["defenses_disabled"] = defenses_disabled
    return out
