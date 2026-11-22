"""Cascade loop (docs/stack.md 4.3): open the cut, split into islands, settle each island's frequency,
recompute the DC flow and open the most overloaded line, until nothing is overloaded. When the 25F corridor
separates with a pre-fault flow beyond the defence-scheme range, the islands at both ends collapse by voltage.

Result: a timeline dict in the stack.md section 6 format (frames are one per cascade stage, not 10 Hz, to keep
files small; frequency curves are sampled at 5 Hz).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import numpy as np

from cascadasen.domain.simulation.params import value

from .flow import dc_flow, find_islands
from .frequency import IslandInput, IslandResult, Params, cascade_params, edac_tables, simulate_island
from .network import ReducedNetwork
from .scenario import OperatingPoint

ASSUMPTIONS = [
    "Red reducida: una barra por subestación y solo líneas; los transformadores se pliegan en su nodo (no se modelan sus sobrecargas).",
    "Flujo DC: sin pérdidas, sin tensión ni potencia reactiva. La tensión no se calcula: si el corredor del 25F se separa con un flujo previo fuera del rango de validez del esquema de defensa (1.600 MW N→S, 1.000 MW S→N), las islas de ambos extremos colapsan por tensión. Es una regla, no un cálculo, y es el único corredor con límites publicados.",
    "Una línea se abre cuando supera 120% de su capacidad (supuesto de docs/stack.md 4.3). Las protecciones reales dependen de relés y tiempos que no están en los datos.",
    "Cada etapa de la cascada se separa 1,0 s de la anterior. Es un tiempo ilustrativo, no calculado.",
    "Reserva primaria 4% de la potencia sincrónica en línea con estatismo 5%, constante de tiempo 3 s y amortiguamiento de carga 1,5 %/Hz: supuestos sin calibrar.",
    "La inercia de cada isla es la de las unidades sincrónicas en línea; solar y eólica no aportan. Una unidad que sale antes del transitorio ya no cuenta.",
    "EDAC con los escalones del informe del CEN sobre el 25F (centro-sur y Norte Grande); los MW de cada escalón se interpolan entre demanda baja y alta. El EDAC por contingencia extrema no se modela.",
    "Baterías en modo rápido: retardo 200 ms y rampa 300 ms (stack.md 4.5), sin límite de energía en el transitorio de 20 s.",
    "No hay desconexión de generación por frecuencia o tensión (ride-through) salvo la reducción por sobrefrecuencia de solar y eólica.",
    "Despacho y demanda del punto de operación son simulados o modelados (PyPSA-CL), no medidos.",
]

_C = cascade_params()["cascade"]
VOLTAGE_LIMIT: dict = dict(value(cascade_params()["voltage_limit"]))


@dataclass(frozen=True)
class CascadeParams:
    overload_factor: float = float(value(_C["overload_factor"]))
    max_stages: int = int(value(_C["max_stages"]))
    stage_spacing_s: float = float(value(_C["stage_spacing_s"]))
    local_cut_mw: float = float(value(_C["local_cut_mw"]))
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
    results: dict[frozenset, dict]
    dark: set[int]
    edac_off: frozenset[str] = frozenset()
    extra_reserve: np.ndarray | None = None
    battery: np.ndarray | None = None
    prefault_boundary_mw: float = 0.0  # pre-fault flow across the 25F boundary, positive north to south
    voltage_ends: tuple[int, int] | None = None  # 25F corridor ends whose separation collapses both islands


@dataclass
class CascadeState:
    """Per-bus state after the cascade settles (the strategic theatre continues from it)."""

    gen: np.ndarray
    load: np.ndarray
    sync: np.ndarray
    inertia: np.ndarray
    open_lines: set[str]
    dark: set[int]
    islands: list[dict] = field(default_factory=list)  # settled islands: `bus_idx` plus the summary fields


def run_cascade_workflow(
    net: ReducedNetwork,
    point: OperatingPoint,
    cut_line_ids: list[str],
    params: CascadeParams = CascadeParams(),
) -> dict:
    """Why: tell what a cut costs (islands, load lost, people in the dark) with calculated physics."""
    return run_cascade_state(net, point, cut_line_ids, params)[0]


def run_cascade_state(
    net: ReducedNetwork,
    point: OperatingPoint,
    cut_line_ids: list[str],
    params: CascadeParams = CascadeParams(),
    *,
    open_lines: frozenset[str] | set[str] = frozenset(),
    edac_off: frozenset[str] | set[str] = frozenset(),
    extra_reserve_by_bus: np.ndarray | None = None,
    battery_by_bus: np.ndarray | None = None,
) -> tuple[dict, CascadeState]:
    """The cascade from a running state: `open_lines` were already open (no cut event), `edac_off`
    zones do not shed, `extra_reserve_by_bus` adds fast reserve and `battery_by_bus` fast-frequency
    batteries to each island. Returns the timeline (same format as `run_cascade_workflow`) and the
    settled per-bus state."""
    state = _start(net, point, params, cut_line_ids, set(open_lines))
    state.edac_off, state.extra_reserve, state.battery = (
        frozenset(edac_off),
        extra_reserve_by_bus,
        battery_by_bus,
    )
    already = set(open_lines)
    state.prefault_boundary_mw = boundary_flow_mw(net, already, point.gen - point.load)
    state.voltage_ends = _voltage_ends(net, already, state.prefault_boundary_mw)
    truncated = _cascade(state)
    final = CascadeState(
        state.gen,
        state.load,
        state.sync,
        state.inertia,
        set(state.open_lines),
        set(state.dark),
        [{"bus_idx": sorted(k), **v} for k, v in state.results.items()],
    )
    return _timeline(state, cut_line_ids, truncated), final


def boundary_lines(net: ReducedNetwork) -> list[tuple[str, int]]:
    """Lines crossing the 25F boundary (between Nueva Maitencillo and Nueva Pan de Azúcar), each with
    +1 when its `a` end is on the north side, so sign * flow is the north-to-south flow."""
    lat = {_plain(name): net.lat[i] for name, i in net.index.items()}
    north = next((v for k, v in lat.items() if k.endswith(_plain(VOLTAGE_LIMIT["north"]))), None)
    south = next((v for k, v in lat.items() if k.endswith(_plain(VOLTAGE_LIMIT["south"]))), None)
    if north is None or south is None:
        return []
    mid = (north + south) / 2
    out = []
    for ln in net.lines:
        a_north, b_north = net.lat[ln.a] > mid, net.lat[ln.b] > mid
        if a_north != b_north:
            out.append((ln.id, 1 if a_north else -1))
    return out


def _plain(name: str) -> str:
    """Upper case without accents: 'Nueva Pan de Azúcar' matches 'S/E NUEVA PAN DE AZUCAR'."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()


def boundary_flow_mw(net: ReducedNetwork, open_lines: set[str], injection: np.ndarray) -> float:
    """Pre-fault DC flow across the 25F boundary, positive north to south."""
    crossing = boundary_lines(net)
    if not crossing:
        return 0.0
    flows = dc_flow(net, open_lines, injection, find_islands(net, open_lines))
    pos = {ln.id: k for k, ln in enumerate(net.lines)}
    return float(sum(sign * flows[pos[lid]] for lid, sign in crossing if lid not in open_lines))


def _voltage_ends(net: ReducedNetwork, already_open: set[str], prefault_mw: float) -> tuple[int, int] | None:
    """stack.md 4.6: the DC model has no voltage. With a pre-fault flow beyond the defence-scheme range across the
    25F boundary, separating its two ends collapses the islands on both sides. Returns those end buses, or None
    when the flow is inside the range or the ends were already apart before this run."""
    over = prefault_mw > VOLTAGE_LIMIT["limit_ns_mw"] or -prefault_mw > VOLTAGE_LIMIT["limit_sn_mw"]
    ends = _end_buses(net)
    if not over or ends is None:
        return None
    together = any(ends[0] in i and ends[1] in i for i in find_islands(net, already_open))
    return ends if together else None


def _end_buses(net: ReducedNetwork) -> tuple[int, int] | None:
    by_name = {_plain(name): i for name, i in net.index.items()}
    found = [
        next((i for k, i in by_name.items() if k.endswith(_plain(VOLTAGE_LIMIT[side]))), None)
        for side in ("north", "south")
    ]
    return (found[0], found[1]) if None not in found else None


def _start(net, point, params, cut_ids, already_open: set[str] | None = None) -> _State:
    known = {ln.id for ln in net.lines}
    unknown = (set(cut_ids) | (already_open or set())) - known
    if unknown:
        raise ValueError(f"unknown line ids: {sorted(unknown)}")
    state = _State(
        net,
        point,
        params,
        point.gen.copy(),
        point.load.copy(),
        point.sync_mw.copy(),
        point.inertia_mws.copy(),
        set(cut_ids) | (already_open or set()),
        [],
        [],
        {},
        {},
        set(),
    )
    if cut_ids:
        state.events.append(
            {"t": 0.0, "type": "line_cut", "ids": list(cut_ids), "text_key": "line_cut", "params": {}}
        )
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
        s.events.append(
            {
                "t": round(t + s.params.stage_spacing_s, 2),
                "type": "line_overload_open",
                "ids": sorted(over),
                "text_key": "line_overload_open",
                "params": {"stage": stage + 1},
            }
        )
    return True


def _most_overloaded(s: _State, flows: np.ndarray) -> list[str]:
    ratios = [
        (abs(f) / ln.capacity_mw if ln.capacity_mw > 0 else 0.0, ln.id)
        for f, ln in zip(flows, s.net.lines, strict=True)
        if ln.id not in s.open_lines
    ]
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
        s.events.append(
            {
                "t": round(t, 2),
                "type": "island_formed",
                "ids": [],
                "text_key": "island_formed",
                "params": {"buses": len(island), "gen_mw": round(gen), "load_mw": round(load)},
            }
        )
        s.results[key] = _settle_island(s, island, gen, load, t)


def _info(
    result: str,
    min_hz: float | None,
    inertia: float,
    final_hz: float | None = None,
    rocof: float | None = None,
    shed_mw: float = 0.0,
    battery_mw: float = 0.0,
) -> dict:
    """Summary of one settled island (timeline `summary.islands` and the theatre's island list)."""
    return {
        "result": result,
        "min_hz": min_hz,
        "final_hz": final_hz,
        "rocof_hz_s": rocof,
        "inertia_mws": round(inertia),
        "shed_mw": round(shed_mw, 1),
        "battery_mw": round(battery_mw, 1),
    }


def _settle_island(s: _State, island: list[int], gen: float, load: float, t: float) -> dict:
    inertia, sync = float(s.inertia[island].sum()), float(s.sync[island].sum())
    if s.voltage_ends and (s.voltage_ends[0] in island) != (s.voltage_ends[1] in island):
        return _lose_island(s, island, t, "blackout", None, "voltage", inertia)
    if gen < 0.5:
        return _lose_island(s, island, t, "dark", None, "no_generation", inertia)
    if load < 0.5:
        return _lose_island(s, island, t, "dark", None, "no_load", inertia)
    if inertia <= 0 or sync <= 0:
        result = "local_cut" if load < s.params.local_cut_mw else "blackout"
        return _lose_island(s, island, t, result, None, "no_inertia", inertia)
    if abs(gen - load) < 1.0:
        return _info("maintains", F0_HZ, inertia, F0_HZ, 0.0)
    sim = simulate_island(_island_input(s, island, inertia, sync, gen, load), s.params.frequency)
    return _apply_result(s, island, sim, t)


F0_HZ = 50.0


def _island_input(
    s: _State, island: list[int], inertia: float, sync: float, gen: float, load: float
) -> IslandInput:
    system_zone = zone_load(s.net, s.point.load, list(range(s.net.size)))
    edac = {
        z: steps
        for z, steps in edac_tables(system_zone, float(s.point.load.sum())).items()
        if z not in s.edac_off
    }
    extra = float(s.extra_reserve[island].sum()) if s.extra_reserve is not None else 0.0
    battery = float(s.battery[island].sum()) if s.battery is not None else 0.0
    return IslandInput(
        inertia,
        sync,
        gen,
        load,
        float(s.gen[island].sum() - s.sync[island].sum()),
        zone_load(s.net, s.load, island),
        edac,
        extra,
        battery,
    )


def zone_load(net: ReducedNetwork, load: np.ndarray, buses: list[int]) -> dict[str, float]:
    out = {"norte_grande": 0.0, "centro_sur": 0.0}
    for b in buses:
        out[net.zone(b)] += float(load[b])
    return out


def _apply_result(s: _State, island: list[int], sim: IslandResult, t: float) -> dict:
    s.curves[f"I{len(s.curves) + 1}"] = [[round(t + p[0], 2), p[1]] for p in sim.curve]
    for step in sim.steps:
        params = {"zone": step["zone"], "step": step["step"], "mw": step["mw"]}
        s.events.append(
            {
                "t": round(t + step["t"], 2),
                "type": "load_shed",
                "ids": [],
                "text_key": "load_shed",
                "params": params,
            }
        )
    shed = sum(sim.shed_mw.values())
    if sim.outcome == "blackout":
        info = _lose_island(
            s, island, t + (sim.collapse_t or 0.0), "blackout", sim.min_hz, "frequency", sim.inertia_mws
        )
        info.update(rocof_hz_s=sim.rocof_hz_s, shed_mw=round(shed, 1))
        return info
    _shed_load(s, island, sim.shed_mw)
    _share_reserve(s, island, sim)
    s.events.append(
        {
            "t": round(t + s.params.frequency.horizon_s, 2),
            "type": "island_stable",
            "ids": [],
            "text_key": "island_stable",
            "params": {"min_hz": sim.min_hz, "final_hz": sim.final_hz, "rocof_hz_s": sim.rocof_hz_s},
        }
    )
    return _info("maintains", sim.min_hz, sim.inertia_mws, sim.final_hz, sim.rocof_hz_s, shed, sim.battery_mw)


def _lose_island(
    s: _State, island: list[int], t: float, result: str, min_hz: float | None, reason: str, inertia: float
) -> dict:
    lost = float(s.load[island].sum())
    s.gen[island] = 0.0
    s.load[island] = 0.0
    s.sync[island] = 0.0
    s.inertia[island] = 0.0
    s.dark.update(island)
    s.events.append(
        {
            "t": round(t, 2),
            "type": "island_blackout",
            "ids": [],
            "text_key": "island_blackout",
            "params": {"buses": len(island), "load_mw": round(lost), "reason": reason, "min_hz": min_hz},
        }
    )
    return {**_info(result, min_hz, inertia), "reason": reason}


def _shed_load(s: _State, island: list[int], shed_mw: dict[str, float]) -> None:
    for zone, mw in shed_mw.items():
        buses = [b for b in island if s.net.zone(b) == zone and s.load[b] > 0]
        total = float(s.load[buses].sum()) if buses else 0.0
        if total > 0:
            s.load[buses] *= max(0.0, 1.0 - mw / total)


def _share_reserve(s: _State, island: list[int], sim: IslandResult) -> None:
    """Deployed primary reserve stays on the synchronous units that delivered it (gen and sync), so the
    theatre does not count it as solar or wind. Battery output is not kept: after the transient the
    island's slack takes over (secondary control is not modelled)."""
    sync = s.sync[island]
    if sync.sum() > 0:
        share = sim.reserve_mw * sync / sync.sum()
        s.gen[island] += share
        s.sync[island] += share
    nonsync = np.maximum(s.gen[island] - s.sync[island], 0.0)
    if nonsync.sum() > 0 and sim.curtailed_mw > 0:
        s.gen[island] -= sim.curtailed_mw * nonsync / nonsync.sum()


def _frame(s: _State, islands: list[list[int]], flows: np.ndarray, t: float) -> dict:
    edges = {}
    for f, ln in zip(flows, s.net.lines, strict=True):
        ratio = abs(f) / ln.capacity_mw if ln.capacity_mw > 0 else 0.0
        status = "open" if ln.id in s.open_lines else ("overload" if ratio > 1.0 else "ok")
        if status != "ok" or abs(f) >= 5:
            edges[ln.id] = {"flow_mw": round(float(f)), "status": status, "loading": round(ratio, 3)}
    return {
        "t": round(t, 2),
        "edges": edges,
        "dark": sorted(f"B{b:03d}" for b in s.dark),
        "islands": [
            {
                "buses": len(i),
                "gen_mw": round(float(s.gen[i].sum())),
                "load_mw": round(float(s.load[i].sum())),
            }
            for i in islands
            if len(i) > 1
        ],
    }


def _timeline(s: _State, cut_ids: list[str], truncated: bool) -> dict:
    initial, final = s.point.load, s.load
    served = np.divide(final, initial, out=np.ones_like(final), where=initial > 0)
    people = float((s.point.people * (1.0 - served)).sum())
    return {
        "scenario": s.point.id,
        "label": s.point.label,
        "failed_elements": cut_ids,
        "truncated": truncated,
        "duration_s": round(s.frames[-1]["t"] + s.params.frequency.horizon_s, 1),
        "events": sorted(s.events, key=lambda e: e["t"]),
        "frames": s.frames,
        "frequency_hz": s.curves,
        "summary": {
            "people_without_power": round(people),
            "load_shed_mw": round(float((initial - final).sum())),
            "load_total_mw": round(float(initial.sum())),
            "stages": len(s.frames) - 1,
            "lines_opened": sorted(s.open_lines),
            "dark_buses": len(s.dark),
            "islands": [{**v, "buses": len(k)} for k, v in s.results.items()],
            "prefault_boundary_mw": round(s.prefault_boundary_mw),
        },
        "assumptions": ASSUMPTIONS,
    }
