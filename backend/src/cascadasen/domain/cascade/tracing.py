"""Who feeds whom: proportional sharing of the power flow (Bialek's downstream tracing), on the DC flow of the grid as it stands (base case, or after the user's changes and their cascade).

Why: the grid data says where the people are and where each plant is, but not which plant supplies which people. The DC
flow knows how much power crosses every line. If the power that enters a substation mixes in proportion to where it
came from, the share of the load at substation j that was generated at g is `c[j, g]`. Multiply by the people at j and
add up: the people that depend on g. (The MW it feeds equal its own generation, because the flow has no losses, so only people are reported.)

ASSUMPTION: proportional sharing. It is a convention, not a measurement of the real system (power does not carry a
label), and the DC flow has no losses, so each substation's inflow plus its own generation equals its load plus its outflow.
"""

from __future__ import annotations

import numpy as np

from .flow import dc_flow, find_islands
from .network import ReducedNetwork

_EPS = 1e-6  # MW; flows below this do not carry a share


def generation_shares(net: ReducedNetwork, gen: np.ndarray, flows: np.ndarray) -> np.ndarray:
    """c[j, g]: share of the power through substation j that was generated at substation g (rows sum to 1, or 0 if no power passes)."""
    n = net.size
    inflow = np.zeros(n)
    edges: list[tuple[int, int, float]] = []
    for f, line in zip(flows, net.lines, strict=True):
        if abs(f) < _EPS:
            continue
        src, dst = (line.a, line.b) if f > 0 else (line.b, line.a)
        edges.append((src, dst, abs(float(f))))
        inflow[dst] += abs(float(f))
    through = gen + inflow
    inflow_share = np.zeros((n, n))  # D[j, k]: share of the power through j that arrives from k
    for src, dst, mw in edges:
        if through[dst] > _EPS:
            inflow_share[dst, src] += mw / through[dst]
    own = np.where(through > _EPS, gen / np.where(through > _EPS, through, 1.0), 0.0)
    return np.linalg.solve(np.eye(n) - inflow_share, np.diag(own))


def dependency_workflow(
    net: ReducedNetwork,
    gen: np.ndarray,
    load: np.ndarray,
    people: np.ndarray,
    open_lines: frozenset[str] = frozenset(),
) -> list[dict]:
    """For every substation with generation: the people that depend on it and their share of the country.
    `open_lines` are out of service (the user's cuts and what the cascade opened)."""
    flows = dc_flow(net, set(open_lines), gen - load, find_islands(net, set(open_lines)))
    c = generation_shares(net, gen, flows)
    people_fed = people @ c
    total_people = float(people.sum()) or 1.0
    return [
        {
            "bus": f"B{g:03d}",
            "gen_mw": round(float(gen[g]), 1),
            "people_fed": round(float(people_fed[g])),
            "share_of_people": round(float(people_fed[g]) / total_people, 4),
        }
        for g in range(net.size)
        if gen[g] > 0.5
    ]
