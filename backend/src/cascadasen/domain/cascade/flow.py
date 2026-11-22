"""DC power flow per island (flow proportional to angle difference over reactance), solved with numpy."""

from __future__ import annotations

import numpy as np

from .network import ReducedNetwork

BASE_MVA = 100.0


def find_islands(net: ReducedNetwork, open_lines: set[str]) -> list[list[int]]:
    parent = list(range(net.size))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for ln in net.lines:
        if ln.id not in open_lines:
            parent[root(ln.a)] = root(ln.b)
    groups: dict[int, list[int]] = {}
    for i in range(net.size):
        groups.setdefault(root(i), []).append(i)
    return sorted(groups.values(), key=len, reverse=True)


def dc_flow(
    net: ReducedNetwork, open_lines: set[str], injection_mw: np.ndarray, islands: list[list[int]]
) -> np.ndarray:
    """Flow in MW per line (positive from a to b). Each island has its own slack, which absorbs any residual."""
    flows = np.zeros(len(net.lines))
    position = {ln.id: k for k, ln in enumerate(net.lines)}
    for island in islands:
        if len(island) < 2:
            continue
        local = {bus: i for i, bus in enumerate(island)}
        active = [ln for ln in net.lines if ln.id not in open_lines and ln.a in local]
        theta = _angles(active, local, injection_mw[island])
        for ln in active:
            flows[position[ln.id]] = BASE_MVA * (theta[local[ln.a]] - theta[local[ln.b]]) / ln.x_pu
    return flows


def _angles(active, local, injection: np.ndarray) -> np.ndarray:
    n = len(local)
    laplacian = np.zeros((n, n))
    for ln in active:
        i, j, w = local[ln.a], local[ln.b], 1.0 / ln.x_pu
        laplacian[i, i] += w
        laplacian[j, j] += w
        laplacian[i, j] -= w
        laplacian[j, i] -= w
    slack = int(np.argmax(np.abs(injection)))
    keep = [i for i in range(n) if i != slack]
    theta = np.zeros(n)
    reduced, rhs = laplacian[np.ix_(keep, keep)], injection[keep] / BASE_MVA
    # The reduced Laplacian of a connected island with every x_pu > 0 is positive definite, so an LU solve gives
    # the same angles as least squares (within float noise) at a fraction of the cost; lstsq stays as a fallback.
    try:
        theta[keep] = np.linalg.solve(reduced, rhs)
    except np.linalg.LinAlgError:
        theta[keep] = np.linalg.lstsq(reduced, rhs, rcond=None)[0]
    return theta
