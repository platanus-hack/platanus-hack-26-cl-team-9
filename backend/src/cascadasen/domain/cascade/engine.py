"""Cascade loop (docs/stack.md 4.3): open the cut, split into islands, settle each island's frequency,
recompute the DC flow and open the most overloaded line, until nothing is overloaded.

Result: a timeline dict in the stack.md section 6 format (frames are one per cascade stage, not 10 Hz, to keep
files small; frequency curves are sampled at 5 Hz).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .flow import dc_flow, find_islands
from .frequency import IslandInput, IslandResult, Params, edac_tables, simulate_island
from .network import ReducedNetwork
from .scenario import OperatingPoint

ASSUMPTIONS = [
    "Red reducida: una barra por subestación y solo líneas; los transformadores se pliegan en su nodo (no se modelan sus sobrecargas).",
    "Flujo DC: sin pérdidas, sin tensión ni potencia reactiva. El colapso de tensión del norte del 25F no se calcula.",
    "Una línea se abre cuando supera 120% de su capacidad (supuesto de docs/stack.md 4.3). Las protecciones reales dependen de relés y tiempos que no están en los datos.",
    "Cada etapa de la cascada se separa 1,0 s de la anterior. Es un tiempo ilustrativo, no calculado.",
    "Reserva primaria 4% de la potencia sincrónica en línea, amortiguamiento de carga 1,5 %/Hz y constante de tiempo 3 s: supuestos sin calibrar.",
    "EDAC con los escalones del informe del CEN sobre el 25F; los MW de cada escalón se interpolan entre demanda baja y alta según la demanda del punto.",
    "No hay desconexión de generación por frecuencia o tensión (ride-through) salvo la reducción por sobrefrecuencia de solar y eólica.",
    "Despacho y demanda del punto de operación son simulados o modelados (PyPSA-CL), no medidos.",
]


@dataclass(frozen=True)
class CascadeParams:
    overload_factor: float = 1.2
    max_stages: int = 20
    stage_spacing_s: float = 1.0
    local_cut_mw: float = 200.0
    frequency: Params = field(default_factory=Params)


@dataclass
class _State:
    net: ReducedNetwork
    point: OperatingPoint
    params: CascadeParams
    gen: np.ndarray
    load: np.ndarray
    sync: np.ndarray
    inertia: np.ndarray
    open_lines: set[str]
    events: list[dict]
    frames: list[dict]
    curves: dict[str, list[list[float]]]
    results: dict[frozenset, tuple[str, float | None]]
    dark: set[int]


def run_cascade_workflow(net: ReducedNetwork, point: OperatingPoint, cut_line_ids: list[str],
                         params: CascadeParams = CascadeParams()) -> dict:
    """Why: tell what a cut costs (islands, load lost, people in the dark) with calculated physics."""
    state = _start(net, point, params, cut_line_ids)
    truncated = _cascade(state)
    return _timeline(state, cut_line_ids, truncated)


def _start(net, point, params, cut_ids) -> _State:
    known = {ln.id for ln in net.lines}
    unknown = set(cut_ids) - known
    if unknown:
        raise ValueError(f"unknown line ids: {sorted(unknown)}")
    state = _State(net, point, params, point.gen.copy(), point.load.copy(), point.sync_mw.copy(), point.inertia_mws.copy(),
                   set(cut_ids), [], [], {}, {}, set())
    state.events.append({"t": 0.0, "type": "line_cut", "ids": list(cut_ids), "text_key": "line_cut", "params": {}})
    return state


def _cascade(s: _State) -> bool:
    for stage in range(s.params.max_stages + 1):
        t = stage * s.params.stage_spacing_s
        islands = find_islands(s.net, s.open_lines)
        _settle_islands(s, islands, t)
        flows = dc_flow(s.net, s.open_lines, s.gen - s.load, islands)
        s.frames.append(_frame(s, islands, flows, t))
        over = _most_overloaded(s, flows)
        if not over:
            return False
        s.open_lines.update(over)
        s.events.append({"t": round(t + s.params.stage_spacing_s, 2), "type": "line_overload_open", "ids": sorted(over),
                         "text_key": "line_overload_open", "params": {"stage": stage + 1}})
    return True


def _most_overloaded(s: _State, flows: np.ndarray) -> list[str]:
    ratios = [(abs(f) / ln.capacity_mw if ln.capacity_mw > 0 else 0.0, ln.id) for f, ln in zip(flows, s.net.lines) if ln.id not in s.open_lines]
    worst = max(ratios, default=(0.0, ""))[0]
    if worst <= s.params.overload_factor:
        return []
    return [lid for r, lid in ratios if r >= worst - 1e-6]


def _settle_islands(s: _State, islands: list[list[int]], t: float) -> None:
    for island in islands:
        key = frozenset(island)
        gen, load = float(s.gen[island].sum()), float(s.load[island].sum())
        if key in s.results or (gen < 0.5 and load < 0.5):
            continue
        s.events.append({"t": round(t, 2), "type": "island_formed", "ids": [], "text_key": "island_formed",
                         "params": {"buses": len(island), "gen_mw": round(gen), "load_mw": round(load)}})
        s.results[key] = _settle_island(s, island, gen, load, t)


def _settle_island(s: _State, island: list[int], gen: float, load: float, t: float) -> tuple[str, float | None]:
    inertia, sync = float(s.inertia[island].sum()), float(s.sync[island].sum())
    if gen < 0.5:
        return _lose_island(s, island, t, "dark", None, "no_generation")
    if load < 0.5:
        return _lose_island(s, island, t, "dark", None, "no_load")
    if inertia <= 0 or sync <= 0:
        result = "local_cut" if load < s.params.local_cut_mw else "blackout"
        return _lose_island(s, island, t, result, None, "no_inertia")
    if abs(gen - load) < 1.0:
        return "maintains", F0_HZ
    sim = simulate_island(_island_input(s, island, inertia, sync, gen, load), s.params.frequency)
    return _apply_result(s, island, sim, t)


F0_HZ = 50.0


def _island_input(s: _State, island: list[int], inertia: float, sync: float, gen: float, load: float) -> IslandInput:
    system_zone = _zone_load(s.net, s.point.load, list(range(s.net.size)))
    return IslandInput(inertia, sync, gen, load, float(s.gen[island].sum() - s.sync[island].sum()),
                       _zone_load(s.net, s.load, island), edac_tables(system_zone, float(s.point.load.sum())))


def _zone_load(net: ReducedNetwork, load: np.ndarray, buses: list[int]) -> dict[str, float]:
    out = {"norte_grande": 0.0, "centro_sur": 0.0}
    for b in buses:
        out[net.zone(b)] += float(load[b])
    return out


def _apply_result(s: _State, island: list[int], sim: IslandResult, t: float) -> tuple[str, float | None]:
    s.curves[f"I{len(s.curves) + 1}"] = [[round(t + p[0], 2), p[1]] for p in sim.curve]
    for step in sim.steps:
        s.events.append({"t": round(t + step["t"], 2), "type": "load_shed", "ids": [], "text_key": "load_shed",
                         "params": {"zone": step["zone"], "step": step["step"], "mw": step["mw"]}})
    if sim.outcome == "blackout":
        return _lose_island(s, island, t + (sim.collapse_t or 0.0), "blackout", sim.min_hz, "frequency")
    _shed_load(s, island, sim.shed_mw)
    _share_reserve(s, island, sim)
    s.events.append({"t": round(t + s.params.frequency.horizon_s, 2), "type": "island_stable", "ids": [],
                     "text_key": "island_stable", "params": {"min_hz": sim.min_hz, "final_hz": sim.final_hz}})
    return "maintains", sim.min_hz


def _lose_island(s: _State, island: list[int], t: float, result: str, min_hz: float | None, reason: str) -> tuple[str, float | None]:
    lost = float(s.load[island].sum())
    s.gen[island] = 0.0
    s.load[island] = 0.0
    s.sync[island] = 0.0
    s.inertia[island] = 0.0
    s.dark.update(island)
    s.events.append({"t": round(t, 2), "type": "island_blackout", "ids": [], "text_key": "island_blackout",
                     "params": {"buses": len(island), "load_mw": round(lost), "reason": reason, "min_hz": min_hz}})
    return result, min_hz


def _shed_load(s: _State, island: list[int], shed_mw: dict[str, float]) -> None:
    for zone, mw in shed_mw.items():
        buses = [b for b in island if s.net.zone(b) == zone and s.load[b] > 0]
        total = float(s.load[buses].sum()) if buses else 0.0
        if total > 0:
            s.load[buses] *= max(0.0, 1.0 - mw / total)


def _share_reserve(s: _State, island: list[int], sim: IslandResult) -> None:
    sync = s.sync[island]
    if sync.sum() > 0:
        s.gen[island] += sim.reserve_mw * sync / sync.sum()
    nonsync = np.maximum(s.gen[island] - s.sync[island], 0.0)
    if nonsync.sum() > 0 and sim.curtailed_mw > 0:
        s.gen[island] -= sim.curtailed_mw * nonsync / nonsync.sum()


def _frame(s: _State, islands: list[list[int]], flows: np.ndarray, t: float) -> dict:
    edges = {}
    for f, ln in zip(flows, s.net.lines):
        ratio = abs(f) / ln.capacity_mw if ln.capacity_mw > 0 else 0.0
        status = "open" if ln.id in s.open_lines else ("overload" if ratio > 1.0 else "ok")
        if status != "ok" or abs(f) >= 5:
            edges[ln.id] = {"flow_mw": round(float(f)), "status": status, "loading": round(ratio, 3)}
    return {"t": round(t, 2), "edges": edges, "dark": sorted(f"B{b:03d}" for b in s.dark),
            "islands": [{"buses": len(i), "gen_mw": round(float(s.gen[i].sum())), "load_mw": round(float(s.load[i].sum()))}
                        for i in islands if len(i) > 1]}


def _timeline(s: _State, cut_ids: list[str], truncated: bool) -> dict:
    initial, final = s.point.load, s.load
    served = np.divide(final, initial, out=np.ones_like(final), where=initial > 0)
    people = float((s.point.people * (1.0 - served)).sum())
    return {"scenario": s.point.id, "label": s.point.label, "failed_elements": cut_ids, "truncated": truncated,
            "duration_s": round(s.frames[-1]["t"] + s.params.frequency.horizon_s, 1), "events": sorted(s.events, key=lambda e: e["t"]),
            "frames": s.frames, "frequency_hz": s.curves,
            "summary": {"people_without_power": round(people), "load_shed_mw": round(float((initial - final).sum())),
                        "load_total_mw": round(float(initial.sum())), "stages": len(s.frames) - 1,
                        "lines_opened": sorted(s.open_lines), "dark_buses": len(s.dark),
                        "islands": [{"result": r, "min_hz": h, "buses": len(k)} for k, (r, h) in s.results.items()]},
            "assumptions": ASSUMPTIONS}
