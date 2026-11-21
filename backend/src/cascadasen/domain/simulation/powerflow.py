"""Island detection and DC power flow on the reduced network (docs/stack.md 4.2).

Flow on corridor a-b is positive from `a` (north) to `b` (south). Each island is solved on its
own; an island's residual imbalance is spread over its synchronous generation (primary response)
so the DC equations stay solvable.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from cascadasen.domain.simulation.grid import GridState
from cascadasen.domain.simulation.network import ReducedNetwork


def islands(network: ReducedNetwork, state: GridState) -> list[list[str]]:
    """Energized islands (blackout areas excluded), largest population first, areas north to south."""
    g = nx.Graph()
    live = [a for a in network.order if a not in state.blackout_areas]
    g.add_nodes_from(live)
    for cid, c in network.corridors.items():
        if state.corridor(network, cid) is not None:
            g.add_edge(c.a, c.b)
    order = {a: i for i, a in enumerate(network.order)}
    comps = [sorted(c, key=order.__getitem__) for c in nx.connected_components(g)]
    comps.sort(key=lambda c: (-sum(network.areas[a].population for a in c), order[c[0]]))
    return comps


def balanced_injections(
    state: GridState, island: list[str], injections: dict[str, float]
) -> dict[str, float]:
    """Spread the island's residual over synchronous generation (or evenly when there is none)."""
    residual = sum(injections[a] for a in island)
    sync = {a: state.sync_gen(a) for a in island}
    total = sum(sync.values())
    weights = {a: (sync[a] / total if total > 0 else 1.0 / len(island)) for a in island}
    return {a: injections[a] - residual * weights[a] for a in island}


def dc_flow(
    network: ReducedNetwork, state: GridState, injections: dict[str, float] | None = None
) -> dict[str, float]:
    """MW flow per closed corridor. `injections` defaults to generation minus served load."""
    inj = injections or {a: state.gen(a) - state.served_mw.get(a, 0.0) for a in network.order}
    flows: dict[str, float] = {}
    for island in islands(network, state):
        if len(island) < 2:
            continue
        p = balanced_injections(state, island, inj)
        idx = {a: i for i, a in enumerate(island)}
        n = len(island)
        b = np.zeros((n, n))
        lines = []
        for cid, c in network.corridors.items():
            eff = state.corridor(network, cid)
            if eff is None or c.a not in idx:
                continue
            y = 1.0 / eff[0]
            i, j = idx[c.a], idx[c.b]
            b[i, i] += y
            b[j, j] += y
            b[i, j] -= y
            b[j, i] -= y
            lines.append((cid, i, j, y))
        slack = max(range(n), key=lambda k: (state.sync_gen(island[k]), -k))
        keep = [k for k in range(n) if k != slack]
        pu = np.array([p[a] for a in island]) / network.s_base_mva
        theta = np.zeros(n)
        theta[keep] = np.linalg.solve(b[np.ix_(keep, keep)], pu[keep])
        for cid, i, j, y in lines:
            flows[cid] = float((theta[i] - theta[j]) * y * network.s_base_mva)
    return flows
