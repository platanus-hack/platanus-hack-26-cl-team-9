"""Flow network of another country from declared line ends and line parameters (docs/network-format.md).

Today only Brazil has such a source: the ONS line and substation datasets (docs/regional.md section 6).
Unlike the drawn layer (`regional_reduction`), line ends are not guessed by distance: each line declares
its two ONS bus numbers, and the ONS substation dataset gives every bus a substation and coordinates.

The reduction is Chile's (`cascade/network.py`): one bus per substation (transformers are not in the
data and voltage levels inside a substation are merged), parallel circuits folded into one line.

Units (ONS does not state them; inferred from the magnitudes, see docs/regional.md section 6):
`val_resistencia` and `val_reatancia` are percent on a 100 MVA base, `val_shunt` is Mvar at nominal
voltage. So x_pu = x_pct / 100 with no kV conversion.

Pure functions and data, no I/O.
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cascadasen.domain.cascade.flow import BASE_MVA
from cascadasen.domain.cascade.network import X_MIN_PU
from cascadasen.domain.geo import haversine_km
from cascadasen.domain.naming import ascii_upper, similarity
from cascadasen.domain.regional import RegionalPlant, RegionalSource, RegionalSubstation
from cascadasen.domain.regional_reduction import ATTACH_KM, ReducedRegional, km_xy, nearest

FUZZY_MIN = 0.85  # name similarity accepted for a coordinate fallback (assumption, checked by hand)
TOPOLOGY_SNAP_KM = 3.0  # a drawn-layer bus closer than this to a flow bus is the same substation (A5)
OFFICIAL_KM = 189_308  # MapYourGrid index, Brazil, 220 kV and up (not opened; docs/regional.md section 3)
MIN_KM_FOR_X = 5.0  # shorter circuits are left out of the per-km comparisons (as in validation.py)

_PREFIXES = {"SE", "SUBESTACAO", "UHE", "UTE", "UTN", "PCH", "EOL", "UFV", "USINA"}
_ROMAN = {
    "I": "1",
    "II": "2",
    "III": "3",
    "IV": "4",
    "V": "5",
    "VI": "6",
    "VII": "7",
    "VIII": "8",
    "IX": "9",
    "X": "10",
}


@dataclass(frozen=True)
class OnsLine:
    """One row of LINHA_TRANSMISSAO.csv, raw ONS units."""

    record: str  # cod_equipamento
    name: str
    kind: str  # "ac", "dc" or "ramal"
    kv: float
    length_km: float | None
    r_pct: float | None
    x_pct: float | None
    shunt_mvar: float | None
    amps: float | None  # long duration, with limiting factor (val_capacoperlongacomlimit)
    bus_from: str
    bus_to: str
    sub_from: str
    sub_to: str
    entered: str | None = None  # ISO date
    deactivated: str | None = None


@dataclass(frozen=True)
class OnsBusbar:
    """One row of SUBESTACAO.csv: a busbar (one voltage level) of a substation."""

    number: str  # num_barra
    substation: str  # id_subestacao
    name: str
    kv: float | None
    lat: float | None
    lon: float | None


@dataclass
class OnsDataset:
    lines: list[OnsLine]
    busbars: list[OnsBusbar]
    sources: list[RegionalSource] = field(default_factory=list)


@dataclass
class FlowBus:
    id: str
    name: str
    lat: float
    lon: float
    kv: float
    kv_levels: list[float]
    busbars: list[str]
    coord_source: str  # "ons", "epe_exact" or "epe_fuzzy"
    is_assumption: bool


@dataclass(frozen=True)
class Circuit:
    """One AC or DC circuit between two flow buses, in per unit on BASE_MVA."""

    record: str
    a: str
    b: str
    kv: float
    length_km: float
    r_pu: float | None
    x_pu: float
    b_pu: float | None
    amps: float | None
    capacity_mw: float
    assumed: tuple[str, ...]  # fields filled with a typical value


@dataclass
class FlowLine:
    id: str
    a: str
    b: str
    kv: float
    circuits: int
    length_km: float
    r_pu: float | None
    x_pu: float
    b_pu: float | None
    capacity_a: list[float | None]  # per circuit, in branch order
    capacity_mw: float
    assumed_fields: list[str]
    branches: list[str]


@dataclass
class FlowPlant:
    id: str
    bus: str
    name: str
    mw: float
    tech: str | None
    mw_by_tech: dict[str, float]
    count: int
    sources: list[str]


@dataclass
class FlowNetwork:
    country: str
    as_of: str
    sources: list[RegionalSource]
    buses: list[FlowBus] = field(default_factory=list)
    lines: list[FlowLine] = field(default_factory=list)
    dc_links: list[FlowLine] = field(default_factory=list)
    plants: list[FlowPlant] = field(default_factory=list)
    circuits: list[Circuit] = field(default_factory=list)  # AC, before folding (A5 compares these)
    typical_capacity_mw: dict[float, float] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def build_flow_network(
    dataset: OnsDataset,
    epe_substations: Sequence[RegionalSubstation],
    epe_plants: Sequence[RegionalPlant],
    as_of: str,
    country: str = "BRA",
) -> FlowNetwork:
    """ONS rows -> buses (one per substation), folded AC lines, DC links and plants per bus."""
    net = FlowNetwork(country, as_of, list(dataset.sources))
    rows, excluded = _active(dataset.lines, as_of)
    ramal = [r for r in rows if r.kind == "ramal" or not r.bus_to]
    rows = [r for r in rows if r.kind != "ramal" and r.bus_to]
    if ramal:
        excluded["ramal"] = len(ramal)
        names = ", ".join(sorted({r.sub_from for r in ramal}))
        net.warnings.append(f"{len(ramal)} ramales de línea sin extremo 'para' descartados ({names})")

    by_number = {b.number: b for b in dataset.busbars}
    needed = sorted({n for r in rows for n in (r.bus_from, r.bus_to)})
    coords, coord_stats, coord_warnings = _match_coordinates(
        [by_number[n] for n in needed if n in by_number], dataset.busbars, epe_substations
    )
    net.warnings += coord_warnings

    foreign: dict[tuple[str, float], int] = {}
    located: list[tuple[OnsLine, OnsBusbar, OnsBusbar]] = []
    no_coords = 0
    for r in rows:
        ends = [by_number.get(r.bus_from), by_number.get(r.bus_to)]
        for end, name in zip(ends, (r.sub_from, r.sub_to), strict=True):
            if end is None:
                foreign[(name, r.kv)] = foreign.get((name, r.kv), 0) + 1
        if ends[0] is None or ends[1] is None:
            continue
        if ends[0].substation not in coords or ends[1].substation not in coords:
            no_coords += 1
            continue
        located.append((r, ends[0], ends[1]))
    if foreign:
        excluded["foreign_end"] = sum(foreign.values())
        listed = "; ".join(f"{n} {kv:g} kV ({c})" for (n, kv), c in sorted(foreign.items()))
        net.warnings.append(
            f"{sum(foreign.values())} líneas con un extremo fuera del registro de subestaciones del ONS "
            f"(interconexiones u otro país) descartadas: {listed}"
        )
    if no_coords:
        excluded["no_coordinates"] = no_coords
        net.warnings.append(f"{no_coords} líneas con un extremo sin coordenadas descartadas")

    net.buses = _buses(located, coords, country)
    pos = {b.id: (b.lon, b.lat) for b in net.buses}
    bus_id = lambda bb: f"{country}-{bb.substation}"  # noqa: E731

    ac = [(r, bus_id(f), bus_id(t)) for r, f, t in located if r.kind == "ac"]
    dc = [(r, bus_id(f), bus_id(t)) for r, f, t in located if r.kind == "dc"]
    same = sum(1 for _, a, b in ac + dc if a == b)
    if same:
        excluded["same_substation"] = same
        net.warnings.append(f"{same} líneas con los dos extremos en la misma subestación descartadas")

    net.typical_capacity_mw = _typical_capacity(ac)
    x_per_km = _typical_x_per_km(ac)
    net.circuits = [_circuit(r, a, b, pos, net.typical_capacity_mw, x_per_km) for r, a, b in ac if a != b]
    dc_circuits = [_dc_circuit(r, a, b, pos) for r, a, b in dc if a != b]
    net.lines = _fold_parallel_lines(net.circuits, f"{country}-L")
    net.dc_links = _fold_parallel_lines(dc_circuits, f"{country}-DC")
    net.plants, lost = _attach_plants(net.buses, epe_plants, country)
    if lost:
        net.warnings.append(lost)

    assumed_cap = sum(1 for c in net.circuits if "capacity_mw" in c.assumed)
    if assumed_cap:
        net.warnings.append(
            f"{assumed_cap} circuitos sin capacidad en amperes usan la mediana del ONS para su tensión (supuesto)"
        )
    net.stats = {
        "excluded": excluded,
        "coordinates": coord_stats,
        "assumed": {
            field_name: sum(1 for c in net.circuits if field_name in c.assumed)
            for field_name in ("capacity_mw", "x_pu", "length_km")
        },
    }
    return net


def _active(lines: Iterable[OnsLine], as_of: str) -> tuple[list[OnsLine], dict[str, int]]:
    """Lines in service at `as_of`: not deactivated and already entered (as Chile's `_built_by`)."""
    kept, deactivated, future = [], 0, 0
    for r in lines:
        if r.deactivated:
            deactivated += 1
        elif r.entered and r.entered > as_of:
            future += 1
        else:
            kept.append(r)
    return kept, {"deactivated": deactivated, "future": future}


def _to_per_unit(pct: float | None) -> float | None:
    """ONS percent on a 100 MVA base -> per unit on BASE_MVA (the engine's base, also 100 MVA)."""
    return None if pct is None else pct / 100.0 * (BASE_MVA / 100.0)


def _ohm(pu: float | None, kv: float) -> float | None:
    return None if pu is None else pu * kv * kv / BASE_MVA


def _capacity_mw(kv: float, amps: float) -> float:
    """Three-phase rating sqrt(3) * kV * A, in MVA, used as MW like Chile's s_nom (DC flow, no reactive)."""
    return math.sqrt(3) * kv * amps / 1000.0


def _nearest_kv(table: dict[float, Any], kv: float) -> Any:
    return table[min(table, key=lambda k: (abs(k - kv), -k))]


def _typical_capacity(rows: Iterable[tuple[OnsLine, str, str]]) -> dict[float, float]:
    """Median MW per circuit of the lines of each voltage that state amperes."""
    by_kv: dict[float, list[float]] = {}
    for r, _, _ in rows:
        if r.amps:
            by_kv.setdefault(r.kv, []).append(_capacity_mw(r.kv, r.amps))
    return {kv: round(statistics.median(v), 1) for kv, v in sorted(by_kv.items())}


def _typical_x_per_km(rows: Iterable[tuple[OnsLine, str, str]]) -> dict[float, float]:
    """Median x (pu per km) of the lines of each voltage, to fill a missing or non-positive reactance."""
    by_kv: dict[float, list[float]] = {}
    for r, _, _ in rows:
        x = _to_per_unit(r.x_pct)
        if x and x > 0 and r.length_km and r.length_km >= MIN_KM_FOR_X:
            by_kv.setdefault(r.kv, []).append(x / r.length_km)
    return {kv: statistics.median(v) for kv, v in sorted(by_kv.items())}


def _length(r: OnsLine, a: str, b: str, pos: dict[str, tuple[float, float]]) -> tuple[float, bool]:
    if r.length_km:
        return r.length_km, False
    return round(haversine_km(*pos[a], *pos[b]), 1), True


def _circuit(
    r: OnsLine,
    a: str,
    b: str,
    pos: dict[str, tuple[float, float]],
    typical_mw: dict[float, float],
    x_per_km: dict[float, float],
) -> Circuit:
    assumed: list[str] = []
    length, guessed = _length(r, a, b, pos)
    if guessed:
        assumed.append("length_km")
    x = _to_per_unit(r.x_pct)
    if x is None or x <= 0:
        x = _nearest_kv(x_per_km, r.kv) * length
        assumed.append("x_pu")
    if r.amps:
        cap = _capacity_mw(r.kv, r.amps)
    else:
        cap = _nearest_kv(typical_mw, r.kv)
        assumed.append("capacity_mw")
    return Circuit(
        record=r.record,
        a=min(a, b),
        b=max(a, b),
        kv=r.kv,
        length_km=length,
        r_pu=_to_per_unit(r.r_pct),
        x_pu=x,
        b_pu=_to_per_unit(r.shunt_mvar),
        amps=r.amps or None,  # 0 A is not a rating: shown as missing, like the capacity
        capacity_mw=cap,
        assumed=tuple(assumed),
    )


def _dc_circuit(r: OnsLine, a: str, b: str, pos: dict[str, tuple[float, float]]) -> Circuit:
    """HVDC record: no AC impedance. MW = kV * A per record (pole convention not stated: an assumption)."""
    length, guessed = _length(r, a, b, pos)
    assumed = ["capacity_mw"] + (["length_km"] if guessed else [])
    return Circuit(
        record=r.record,
        a=min(a, b),
        b=max(a, b),
        kv=r.kv,
        length_km=length,
        r_pu=None,
        x_pu=0.0,
        b_pu=None,
        amps=r.amps or None,
        capacity_mw=r.kv * r.amps / 1000.0 if r.amps else 0.0,
        assumed=tuple(assumed),
    )


def _fold_parallel_lines(circuits: Iterable[Circuit], prefix: str) -> list[FlowLine]:
    """Circuits between the same two buses -> one line, as Chile's `_parallel` in cascade/network.py.

    Capacity and susceptance add up; resistance and reactance combine in parallel; x has the floor X_MIN_PU.
    """
    groups: dict[tuple[str, str], list[Circuit]] = {}
    for c in circuits:
        groups.setdefault((c.a, c.b), []).append(c)
    ordered = sorted(groups.items(), key=lambda kv: (-max(c.kv for c in kv[1]), kv[0]))
    out = []
    for i, ((a, b), group) in enumerate(ordered, 1):
        group = sorted(group, key=lambda c: c.record)
        dc = all(c.x_pu == 0 for c in group)
        x = 0.0 if dc else max(1.0 / sum(1.0 / c.x_pu for c in group), X_MIN_PU)
        rs = [c.r_pu for c in group]
        r = None
        if all(v is not None for v in rs):
            r = 0.0 if any(v <= 0 for v in rs) else 1.0 / sum(1.0 / v for v in rs)  # type: ignore[operator]
        bs = [c.b_pu for c in group if c.b_pu is not None]
        out.append(
            FlowLine(
                id=f"{prefix}{i}",
                a=a,
                b=b,
                kv=max(c.kv for c in group),
                circuits=len(group),
                length_km=round(max(c.length_km for c in group), 1),
                r_pu=None if r is None else round(r, 6),
                x_pu=round(x, 6),
                b_pu=round(sum(bs), 6) if bs else None,
                capacity_a=[c.amps for c in group],
                capacity_mw=round(sum(c.capacity_mw for c in group), 1),
                assumed_fields=sorted({f for c in group for f in c.assumed}),
                branches=[c.record for c in group],
            )
        )
    return out


def _normalise_substation_name(name: str | None) -> str:
    """'SE Juazeiro III' -> 'JUAZEIRO 3'; 'S/E Foz do Iguaçu' -> 'FOZ DO IGUACU'."""
    tokens = re.sub(r"[^A-Z0-9 ]", " ", ascii_upper(name)).split()
    while tokens:
        if tokens[0] in _PREFIXES:
            tokens = tokens[1:]
        elif tokens[:2] == ["S", "E"]:
            tokens = tokens[2:]
        else:
            break
    return " ".join(_ROMAN.get(t, t) for t in tokens)


def _match_coordinates(
    needed: Sequence[OnsBusbar],
    busbars: Sequence[OnsBusbar],
    epe: Sequence[RegionalSubstation],
) -> tuple[dict[str, tuple[float, float, str]], dict[str, Any], list[str]]:
    """Coordinates per ONS substation: the ONS dataset first, then an EPE substation by name.

    The fallback tries the exact normalised name, then the best similarity >= FUZZY_MIN, both among EPE
    substations with the same voltage. A substation with neither is listed in the warnings.
    """
    coords: dict[str, tuple[float, float, str]] = {}
    for b in busbars:
        if b.lat is not None and b.lon is not None and b.substation not in coords:
            coords[b.substation] = (b.lon, b.lat, "ons")
    subs = sorted({b.substation for b in needed})
    from_ons = sum(1 for s in subs if s in coords)
    exact = fuzzy = 0
    warnings: list[str] = []
    for b in sorted(needed, key=lambda b: b.substation):
        if b.substation in coords:
            continue
        target = _normalise_substation_name(b.name)
        same_kv = [s for s in epe if b.kv in (s.kv_levels or [s.kv])]
        hit = next((s for s in same_kv if _normalise_substation_name(s.name) == target), None)
        if hit is not None:
            coords[b.substation] = (hit.lon, hit.lat, "epe_exact")
            exact += 1
            continue
        scored = [(similarity(target, _normalise_substation_name(s.name)), s) for s in same_kv]
        score, best = max(scored, key=lambda t: t[0], default=(0.0, None))
        if best is not None and score >= FUZZY_MIN:
            coords[b.substation] = (best.lon, best.lat, "epe_fuzzy")
            fuzzy += 1
            continue
        warnings.append(f"subestación sin coordenadas: {b.name} {b.kv or 0:g} kV (barra {b.number})")
    missing = len(subs) - from_ons - exact - fuzzy
    stats = {
        "substations_needed": len(subs),
        "from_ons": from_ons,
        "from_epe_exact_name": exact,
        "from_epe_fuzzy_name": fuzzy,
        "missing": missing,
        "match_rate": round((len(subs) - missing) / len(subs), 4) if subs else None,
        "fuzzy_min": FUZZY_MIN,
    }
    return coords, stats, warnings


def _buses(
    located: Iterable[tuple[OnsLine, OnsBusbar, OnsBusbar]],
    coords: dict[str, tuple[float, float, str]],
    country: str,
) -> list[FlowBus]:
    members: dict[str, dict[str, OnsBusbar]] = {}
    for r, f, t in located:
        for end in (f, t):
            members.setdefault(end.substation, {})[end.number] = end
        for end in (f, t):  # the line voltage is the busbar voltage when the busbar row has none
            if end.kv is None:
                members[end.substation][end.number] = OnsBusbar(
                    end.number, end.substation, end.name, r.kv, end.lat, end.lon
                )
    out = []
    for sub, bars in sorted(members.items()):
        levels = sorted({b.kv for b in bars.values() if b.kv}, reverse=True)
        top = max(bars.values(), key=lambda b: b.kv or 0)
        lon, lat, how = coords[sub]
        out.append(
            FlowBus(
                id=f"{country}-{sub}",
                name=top.name,
                lat=lat,
                lon=lon,
                kv=levels[0] if levels else 0.0,
                kv_levels=levels,
                busbars=sorted(bars),
                coord_source=how,
                is_assumption=how != "ons",
            )
        )
    return out


def _attach_plants(
    buses: Sequence[FlowBus], plants: Sequence[RegionalPlant], country: str
) -> tuple[list[FlowPlant], str | None]:
    """EPE plants added up at the nearest flow bus within ATTACH_KM (as the drawn layer does)."""
    if not buses or not plants:
        return [], None
    lat0 = float(np.mean([b.lat for b in buses]))
    near, km = nearest(
        km_xy([p.lon for p in plants], [p.lat for p in plants], lat0),
        km_xy([b.lon for b in buses], [b.lat for b in buses], lat0),
    )
    per_bus: dict[int, list[int]] = {}
    lost, lost_mw = 0, 0.0
    for i, p in enumerate(plants):
        if km[i] <= ATTACH_KM:
            per_bus.setdefault(int(near[i]), []).append(i)
        else:
            lost += 1
            lost_mw += p.mw or 0.0
    out = []
    for n, (bi, idx) in enumerate(sorted(per_bus.items(), key=lambda kv: buses[kv[0]].id), 1):
        by_tech: dict[str, float] = {}
        for i in idx:
            tech = plants[i].tech or "otra"
            by_tech[tech] = round(by_tech.get(tech, 0.0) + (plants[i].mw or 0.0), 2)
        top = max(by_tech, key=lambda t: by_tech[t])
        out.append(
            FlowPlant(
                id=f"{country}-G{n}",
                bus=buses[bi].id,
                name=buses[bi].name,
                mw=round(sum(by_tech.values()), 2),
                tech=None if top == "otra" else top,
                mw_by_tech=dict(sorted(by_tech.items())),
                count=len(idx),
                sources=sorted({plants[i].source for i in idx}),
            )
        )
    msg = None
    if lost:
        msg = f"{lost} centrales ({lost_mw:,.0f} MW) a más de {ATTACH_KM:g} km de una barra del flujo descartadas"
    return out, msg


def _errors(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """Relative error |deduced - real| / real: median, p90 and the median signed bias."""
    rel = [(d - r) / r for d, r in pairs if r > 0]
    if not rel:
        return {"n": 0}
    absolute = sorted(abs(e) for e in rel)
    return {
        "n": len(rel),
        "median_abs": round(statistics.median(absolute), 3),
        "p90_abs": round(float(np.percentile(absolute, 90)), 3),
        "median_bias": round(statistics.median(rel), 3),
    }


def deduction_error(
    net: FlowNetwork,
    drawn: ReducedRegional,
    x_ohm_per_km: dict[float, tuple[float, float]],
    typical_mva: dict[float, float],
) -> dict[str, Any]:
    """How far a deduced network is from the real one (docs/network-format.md section 3).

    Parameters: each real AC circuit gets the x and the capacity a country without data would use
    (midpoint of the typical ohm/km range of the nearest class times the length; the typical rating of
    the nearest class) and is compared with the ONS value. Topology: the drawn layer's corridors, whose
    ends were snapped by distance, against the corridors the ONS declares.
    """
    x_by: dict[str, list[tuple[float, float]]] = {}
    cap_by: dict[str, list[tuple[float, float]]] = {}
    for c in net.circuits:
        key = f"{c.kv:g}"
        if "x_pu" not in c.assumed and "length_km" not in c.assumed and c.length_km >= MIN_KM_FOR_X:
            lo, hi = _nearest_kv(x_ohm_per_km, c.kv)
            x_by.setdefault(key, []).append(((lo + hi) / 2 * c.length_km, _ohm(c.x_pu, c.kv) or 0.0))
        if "capacity_mw" not in c.assumed:
            cap_by.setdefault(key, []).append((_nearest_kv(typical_mva, c.kv), c.capacity_mw))

    def table(groups: dict[str, list[tuple[float, float]]]) -> dict[str, Any]:
        rows = {k: _errors(v) for k, v in sorted(groups.items(), key=lambda kv: float(kv[0]))}
        rows["all"] = _errors([p for v in groups.values() for p in v])
        return rows

    return {
        "x": table(x_by),
        "capacity": table(cap_by),
        "topology": _topology_error(net, drawn),
        "method": {
            "x": "midpoint of X_PER_KM (domain/validation.py, nearest class) * length_km",
            "capacity": "typical_capacity_mva (domain/simulation/params/network.yaml, nearest class)",
            "topology": f"drawn-layer buses snapped to the nearest flow bus within {TOPOLOGY_SNAP_KM:g} km",
        },
    }


def _topology_error(net: FlowNetwork, drawn: ReducedRegional) -> dict[str, Any]:
    if not net.buses or not drawn.buses:
        return {}
    lat0 = float(np.mean([b.lat for b in net.buses]))
    near, km = nearest(
        km_xy([b.lon for b in drawn.buses], [b.lat for b in drawn.buses], lat0),
        km_xy([b.lon for b in net.buses], [b.lat for b in net.buses], lat0),
    )
    snap = {b.id: net.buses[int(near[i])].id for i, b in enumerate(drawn.buses) if km[i] <= TOPOLOGY_SNAP_KM}
    reached = set(snap.values())
    ac_kv = {ln.kv for ln in net.lines}
    deduced, unmapped = set(), 0
    for ln in drawn.links:
        if ln.kv not in ac_kv:  # below 230 kV or HVDC: outside what the flow network covers
            continue
        a, b = snap.get(ln.a), snap.get(ln.b)
        if a is None or b is None:
            unmapped += 1
        elif a != b:
            deduced.add(frozenset((a, b)))
    real = {frozenset((ln.a, ln.b)) for ln in net.lines if ln.a in reached and ln.b in reached}
    hit = len(deduced & real)
    return {
        "drawn_buses_snapped": len(snap),
        "drawn_links_compared": len(deduced),
        "drawn_links_unmapped": unmapped,
        "real_links_compared": len(real),
        "true_links": hit,
        "precision": round(hit / len(deduced), 3) if deduced else None,
        "recall": round(hit / len(real), 3) if real else None,
    }


def _source_dict(s: RegionalSource) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "publisher": s.publisher,
        "url": s.url,
        "license": s.license,
        "attribution": s.attribution,
        "provides": list(s.provides),
        "fetched_at": s.fetched_at,
    }


UNITS = {
    "kv": "kV",
    "length_km": "km",
    "r_pu": "pu on base_mva (ONS val_resistencia is percent on 100 MVA)",
    "x_pu": "pu on base_mva (ONS val_reatancia is percent on 100 MVA)",
    "b_pu": "pu on base_mva (ONS val_shunt is Mvar at nominal voltage)",
    "r_ohm": "ohm",
    "x_ohm": "ohm",
    "capacity_a": "A per circuit, long duration with limiting factor (val_capacoperlongacomlimit)",
    "capacity_mw": "MW (sqrt(3) * kV * A; treated as MW like Chile's s_nom_mva)",
    "mw": "MW installed",
}


def _line_dict(ln: FlowLine, country: str, source: str, dc: bool) -> dict[str, Any]:
    note = f"{source}; supuesto: {', '.join(ln.assumed_fields)}" if ln.assumed_fields else source
    out: dict[str, Any] = {
        "id": ln.id,
        "a": ln.a,
        "b": ln.b,
        "kv": ln.kv,
        "circuits": ln.circuits,
        "length_km": ln.length_km,
    }
    if dc:
        out["dc"] = True
    else:
        out |= {
            "r_pu": ln.r_pu,
            "x_pu": ln.x_pu,
            "b_pu": ln.b_pu,
            "r_ohm": None if ln.r_pu is None else round(_ohm(ln.r_pu, ln.kv) or 0.0, 4),
            "x_ohm": round(_ohm(ln.x_pu, ln.kv) or 0.0, 4),
        }
    unknown = dc and all(a is None for a in ln.capacity_a)  # Itaipu HVDC states no amperes
    return out | {
        "capacity_a": ln.capacity_a,
        "capacity_mw": None if unknown else ln.capacity_mw,
        "assumed_fields": ln.assumed_fields,
        "branches": ln.branches,
        "country": country,
        "source": note,
        "is_assumption": bool(ln.assumed_fields),
    }


def network_document(net: FlowNetwork, built_at: str) -> dict[str, Any]:
    """The `network.json` contract (docs/network-format.md section 1)."""
    line_src = "ONS linha-transmissao"
    bus_src = {
        "ons": "ONS subestacao",
        "epe_exact": "ONS subestacao; coordenadas: EPE WebMap por nombre exacto",
        "epe_fuzzy": "ONS subestacao; coordenadas: EPE WebMap por nombre aproximado",
    }
    return {
        "version": 1,
        "country": net.country,
        "built_at": built_at,
        "as_of": net.as_of,
        "base_mva": BASE_MVA,
        "frequency_hz": 60,
        "level": "L1+",
        "units": UNITS,
        "sources": [_source_dict(s) for s in net.sources],
        "typical_capacity_mw": {f"{k:g}": v for k, v in net.typical_capacity_mw.items()},
        "buses": [
            {
                "id": b.id,
                "name": b.name,
                "lat": round(b.lat, 5),
                "lon": round(b.lon, 5),
                "kv": b.kv,
                "kv_levels": b.kv_levels,
                "ons_busbars": b.busbars,
                "coord_source": b.coord_source,
                "country": net.country,
                "source": bus_src[b.coord_source],
                "is_assumption": b.is_assumption,
            }
            for b in net.buses
        ],
        "lines": [_line_dict(ln, net.country, line_src, dc=False) for ln in net.lines],
        "dc_links": [_line_dict(ln, net.country, line_src, dc=True) for ln in net.dc_links],
        "plants": [
            {
                "id": p.id,
                "bus": p.bus,
                "name": p.name,
                "tech": p.tech,
                "mw": p.mw,
                "mw_by_tech": p.mw_by_tech,
                "count": p.count,
                "country": net.country,
                "source": "; ".join(p.sources),
                "is_assumption": False,
            }
            for p in net.plants
        ],
        "warnings": net.warnings,
    }


def _km_by_kv(circuits: Iterable[Circuit]) -> dict[str, float]:
    km: dict[float, float] = {}
    for c in circuits:
        km[c.kv] = km.get(c.kv, 0.0) + c.length_km
    return {f"{kv:g}": round(v, 1) for kv, v in sorted(km.items(), reverse=True)}


def flow_manifest_entry(net: FlowNetwork, built_at: str) -> dict[str, Any]:
    """The `flow` block of a country in data/processed/latam/manifest.json."""
    circuit_km = round(sum(c.length_km for c in net.circuits), 1)
    corridor_km = round(sum(ln.length_km for ln in net.lines), 1)
    dc_records = sum(ln.circuits for ln in net.dc_links)
    dc_km = round(sum(ln.length_km * ln.circuits for ln in net.dc_links), 1)
    return {
        "file": f"{net.country}/network.json",
        "built_at": built_at,
        "as_of": net.as_of,
        "level": "L1+",
        "counts": {
            "buses": len(net.buses),
            "lines": len(net.lines),
            "circuits": len(net.circuits),
            "dc_links": len(net.dc_links),
            "dc_records": dc_records,
            "plants": len(net.plants),
        },
        "circuit_km_by_kv": _km_by_kv(net.circuits),
        "length_check": {
            "circuit_km_ac": circuit_km,
            "corridor_km_ac": corridor_km,
            "dc_km": dc_km,
            "official_km": OFFICIAL_KM,
            "official_source": "MapYourGrid transmission length index, 220 kV and up (CC BY 4.0, not opened)",
            "ac_vs_official": round(circuit_km / OFFICIAL_KM - 1, 3),
            "ac_dc_vs_official": round((circuit_km + dc_km) / OFFICIAL_KM - 1, 3),
        },
        "assumed": net.stats.get("assumed", {}),
        "excluded": net.stats.get("excluded", {}),
        "coordinates": net.stats.get("coordinates", {}),
        "typical_capacity_mw": {f"{k:g}": v for k, v in net.typical_capacity_mw.items()},
        "units": UNITS,
        "sources": [_source_dict(s) for s in net.sources],
        "warnings": net.warnings,
    }


__all__ = [
    "Circuit",
    "FlowBus",
    "FlowLine",
    "FlowNetwork",
    "FlowPlant",
    "OnsBusbar",
    "OnsDataset",
    "OnsLine",
    "build_flow_network",
    "deduction_error",
    "flow_manifest_entry",
    "network_document",
]
