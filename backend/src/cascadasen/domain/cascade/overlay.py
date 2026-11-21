"""Session overlay: a small JSON edit of the 188-bus network and its operating point (docs/stack.md 6.2).

An overlay adds buses (`B###` after the base buses), lines (`U###`), loads and datacenters (`D###`)
and generators (`G###`), overrides base buses and lines, and takes base elements out of service
(they are never deleted). `apply_overlay` validates it and returns the edited network and point.
Every island of the edited network is rebalanced: the change in generation minus load that the edit
causes is redispatched over the base synchronous units of the island, in proportion to their
synchronous MW. That rule is an assumption (`is_assumption: true`), not an OPF.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cascadasen.domain.geo import haversine_km
from cascadasen.domain.theater.areas import bus_id
from cascadasen.domain.validation import X_PER_KM

from .flow import BASE_MVA, find_islands
from .network import X_MIN_PU, Line, ReducedNetwork
from .scenario import OperatingPoint

MAX_ADDED = 50  # buses + lines + loads + generators added by one session
MAX_ELEMENT_MW = 3000.0  # one added load or generator
MAX_ADDED_MW = 5000.0  # sum of added load and generation, plus the MW changed by bus overrides
MAX_CAPACITY_MW = 5000.0
LAT = (-56.0, -17.0)
LON = (-76.0, -66.0)
X_MAX_PU = 1.0
DEFAULT_INERTIA_H = 4.0  # assumption: typical H (s) of a synchronous unit
MAX_INERTIA_H = 10.0  # upper bound of H (s) for added generators and bus inertia overrides
SYNC_TECH = frozenset({"hidro", "termica", "bioenergia", "geotermica"})
TECHS = SYNC_TECH | {"solar", "eolica"}
LOAD_KINDS = frozenset({"datacenter", "consumo"})
UNBALANCED_MW = 1.0  # the engine treats |gen - load| >= 1 MW in an island as a disturbance
BALANCE_RULE = (
    "Redespacho proporcional de las unidades sincrónicas base de la isla (MW sincrónicos); "
    "la inercia no cambia."
)

KINDS = ("bus", "line", "load", "generator")
_LIST = {"bus": "buses", "line": "lines", "load": "loads", "generator": "generators"}
_SEQ = {"line": ("U", "line"), "load": ("D", "load"), "generator": ("G", "generator")}
_ADD_FIELDS = {
    "bus": {"name", "lat", "lon", "kv"},
    "line": {"a", "b", "kv", "capacity_mw", "x_pu", "name"},
    "load": {"bus", "mw", "kind", "name"},
    "generator": {"bus", "mw", "tech", "synchronous", "inertia_h", "name"},
}
_BUS_VALUES = ("load_mw", "gen_mw", "sync_mw", "inertia_mws")
_PATCH_FIELDS = {
    "bus": {"name", "kv", "lat", "lon", *_BUS_VALUES, "in_service"},
    "line": {"capacity_mw", "x_pu", "in_service"},
    "load": {"mw", "kind", "name", "in_service"},
    "generator": {"mw", "tech", "synchronous", "inertia_h", "name", "in_service"},
}


class OverlayError(ValueError):
    """Invalid overlay edit: HTTP 422, 404 when it names something that does not exist, 409 on a
    conflict (removing a base element or a bus that is still referenced)."""

    def __init__(
        self,
        field: str,
        message: str,
        valid: list[str] | None = None,
        not_found: bool = False,
        conflict: bool = False,
    ) -> None:
        super().__init__(message)
        self.field, self.message, self.valid = field, message, valid or []
        self.not_found, self.conflict = not_found, conflict

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {"field": self.field, "message": self.message}
        if self.valid:
            out["valid"] = self.valid
        return out


@dataclass
class Applied:
    net: ReducedNetwork
    point: OperatingPoint
    warnings: list[dict[str, Any]] = field(default_factory=list)
    balance: list[dict[str, Any]] = field(default_factory=list)


def empty_overlay() -> dict[str, Any]:
    return {
        "buses": [],
        "lines": [],
        "loads": [],
        "generators": [],
        "bus_overrides": {},
        "line_overrides": {},
        "seq": {"line": 0, "load": 0, "generator": 0},
    }


def is_empty(overlay: dict[str, Any]) -> bool:
    keys = ("buses", "lines", "loads", "generators", "bus_overrides", "line_overrides")
    return not any(overlay.get(k) for k in keys)


# ------------------------------------------------------------------ edits


def add(
    overlay: dict[str, Any], kind: str, fields: dict[str, Any], net: ReducedNetwork, point: OperatingPoint
) -> tuple[dict[str, Any], str]:
    """A copy of `overlay` with a new element of `kind`, and the element's id."""
    _kind(kind)
    _known_fields(fields, _ADD_FIELDS[kind])
    out = _copy(overlay)
    rec = {k: v for k, v in fields.items() if v is not None}
    if kind == "bus":
        new_id = bus_id(net.size + len(out["buses"]))
    else:
        prefix, counter = _SEQ[kind]
        out["seq"][counter] = int(out["seq"].get(counter, 0)) + 1
        new_id = f"{prefix}{out['seq'][counter]:03d}"
    if kind == "line" and "x_pu" not in rec:
        rec["x_pu"] = _default_x_pu(out, rec, net)
    out[_LIST[kind]].append({"id": new_id, **rec})
    apply_overlay(net, point, out)
    return out, new_id


def patch(
    overlay: dict[str, Any],
    kind: str,
    element_id: str,
    fields: dict[str, Any],
    net: ReducedNetwork,
    point: OperatingPoint,
) -> dict[str, Any]:
    """A copy of `overlay` with `fields` set on an element. A base bus or line gets an override;
    a `None` value clears that field of the override."""
    _kind(kind)
    _known_fields(fields, _PATCH_FIELDS[kind])
    out = _copy(overlay)
    base = _base_ids(kind, net)
    if element_id in base:
        key = "bus_overrides" if kind == "bus" else "line_overrides"
        over = {**out[key].get(element_id, {}), **fields}
        over = {k: v for k, v in over.items() if v is not None}
        if over:
            out[key][element_id] = over
        else:
            out[key].pop(element_id, None)
    else:
        rec = _session_record(out, kind, element_id)
        rec.update(fields)
        for k in [k for k, v in rec.items() if v is None]:
            del rec[k]
    apply_overlay(net, point, out)
    return out


def remove(
    overlay: dict[str, Any], kind: str, element_id: str, net: ReducedNetwork, point: OperatingPoint
) -> dict[str, Any]:
    """A copy of `overlay` without a session element. A session bus leaves a tombstone so later
    bus ids stay stable."""
    _kind(kind)
    if element_id in _base_ids(kind, net):
        raise OverlayError("id", "Los elementos base no se borran: usa in_service=false.", conflict=True)
    out = _copy(overlay)
    rec = _session_record(out, kind, element_id)
    if kind == "bus":
        users = [ln["id"] for ln in out["lines"] if element_id in (ln.get("a"), ln.get("b"))]
        users += [r["id"] for r in out["loads"] + out["generators"] if r.get("bus") == element_id]
        if users:
            raise OverlayError(
                "id", f"La barra aún tiene elementos conectados: {', '.join(users)}.", users, conflict=True
            )
        rec["removed"] = True
    else:
        out[_LIST[kind]] = [r for r in out[_LIST[kind]] if r["id"] != element_id]
    apply_overlay(net, point, out)
    return out


# ------------------------------------------------------------------ apply


def apply_overlay(net: ReducedNetwork, point: OperatingPoint, overlay: dict[str, Any]) -> Applied:
    """The edited network and point, validated and rebalanced per island. Raises `OverlayError`."""
    if is_empty(overlay):
        return Applied(net, point)
    n, added = net.size, overlay.get("buses") or []
    total = n + len(added)
    names, lat, lon, kv = list(net.names), list(net.lat), list(net.lon), list(net.kv)
    kv_set = sorted({float(v) for v in net.kv} | {float(ln.kv) for ln in net.lines})
    pad = np.zeros(len(added))
    base = {
        "load": np.concatenate([point.load, pad]),
        "gen": np.concatenate([point.gen, pad]),
        "sync": np.concatenate([point.sync_mw, pad]),
    }
    load, gen, sync = base["load"].copy(), base["gen"].copy(), base["sync"].copy()
    inertia = np.concatenate([point.inertia_mws, pad])
    people = np.concatenate([point.people, pad])
    in_service = [True] * total
    removed = [False] * total
    pinned: set[int] = set()  # buses whose generation the overlay sets: not redispatched
    added_mw = 0.0

    def edit_bus(i: int, rec: dict[str, Any], where: str) -> None:
        nonlocal added_mw
        if "name" in rec:
            names[i] = _name(rec["name"], f"{where}.name")
        if "kv" in rec:
            kv[i] = _kv(rec["kv"], kv_set, f"{where}.kv")
        if "lat" in rec:
            lat[i] = _number(rec["lat"], f"{where}.lat", *LAT)
        if "lon" in rec:
            lon[i] = _number(rec["lon"], f"{where}.lon", *LON)
        for key, arr, ref in zip(
            _BUS_VALUES[:3], (load, gen, sync), (base["load"], base["gen"], base["sync"]), strict=True
        ):
            if key in rec:
                arr[i] = _number(rec[key], f"{where}.{key}", 0.0, float(ref[i]) + MAX_ELEMENT_MW)
                if key != "sync_mw":
                    added_mw += abs(arr[i] - float(ref[i]))
        if "gen_mw" in rec or "sync_mw" in rec:
            pinned.add(i)
        if sync[i] > gen[i] + 1e-9:
            raise OverlayError(f"{where}.sync_mw", "sync_mw no puede superar gen_mw en la barra.")
        if "inertia_mws" in rec:
            inertia[i] = _number(
                rec["inertia_mws"], f"{where}.inertia_mws", 0.0, MAX_INERTIA_H * float(sync[i])
            )
        if "in_service" in rec:
            in_service[i] = _flag(rec["in_service"], f"{where}.in_service")

    for values in (names, lat, lon, kv):  # slots of the added buses, filled below
        values.extend([""] * len(added) if values is names else [0.0] * len(added))
    for k, rec in enumerate(added):
        i = n + k
        if rec.get("id") != bus_id(i):
            raise OverlayError("buses", f"Id de barra inesperado: {rec.get('id')} (se esperaba {bus_id(i)}).")
        if rec.get("removed"):  # tombstone: keeps its index, carries nothing, hidden from views
            names[i] = str(rec.get("name") or rec["id"])
            lat[i], lon[i] = float(rec.get("lat", 0.0)), float(rec.get("lon", 0.0))
            removed[i], in_service[i] = True, False
            continue
        for key in ("name", "lat", "lon", "kv"):
            _require(rec, key, rec["id"])
        edit_bus(i, rec, rec["id"])

    base_ids = {bus_id(i): i for i in range(n)}
    for bid, rec in (overlay.get("bus_overrides") or {}).items():
        if bid not in base_ids:
            raise OverlayError("bus_overrides", f"Barra base desconocida: {bid}.", not_found=True)
        edit_bus(base_ids[bid], rec, bid)

    for i in range(total):
        if not in_service[i]:
            load[i] = gen[i] = sync[i] = inertia[i] = 0.0

    def bus_index(ref: Any, where: str) -> int:
        i = _bus_ref(ref, total)
        if i is None or removed[i]:
            raise OverlayError(where, f"Barra desconocida: {ref}.", not_found=True)
        if not in_service[i]:
            raise OverlayError(where, f"La barra {ref} está fuera de servicio.")
        return i

    lines: list[Line] = []
    dropped: list[tuple[int, int]] = []  # in-service base lines dropped because a bus is out of service
    line_overrides = overlay.get("line_overrides") or {}
    base_lines = {ln.id for ln in net.lines}
    for lid in line_overrides:
        if lid not in base_lines:
            raise OverlayError("line_overrides", f"Línea base desconocida: {lid}.", not_found=True)
    for ln in net.lines:
        over = line_overrides.get(ln.id) or {}
        if "capacity_mw" in over or "x_pu" in over:
            ln = Line(
                ln.id,
                ln.a,
                ln.b,
                _capacity(over.get("capacity_mw", ln.capacity_mw), f"{ln.id}.capacity_mw"),
                _x_pu(over.get("x_pu", ln.x_pu), f"{ln.id}.x_pu"),
                ln.kv,
                ln.branches,
                ln.map_edges,
            )
        on = _flag(over.get("in_service", True), f"{ln.id}.in_service")
        if on and in_service[ln.a] and in_service[ln.b]:
            lines.append(ln)
        elif on:
            dropped.append((ln.a, ln.b))
    for rec in overlay.get("lines") or []:
        lid = rec["id"]
        for key in ("a", "b", "kv", "capacity_mw", "x_pu"):
            _require(rec, key, lid)
        a, b = bus_index(rec["a"], f"{lid}.a"), bus_index(rec["b"], f"{lid}.b")
        if a == b:
            raise OverlayError(f"{lid}.b", "Una línea necesita dos barras distintas.")
        line = Line(
            lid,
            a,
            b,
            _capacity(rec["capacity_mw"], f"{lid}.capacity_mw"),
            _x_pu(rec["x_pu"], f"{lid}.x_pu"),
            _kv(rec["kv"], kv_set, f"{lid}.kv"),
            (),
            (),
        )
        if _flag(rec.get("in_service", True), f"{lid}.in_service"):
            lines.append(line)

    for rec in overlay.get("loads") or []:
        lid = rec["id"]
        for key in ("bus", "mw", "kind", "name"):
            _require(rec, key, lid)
        i = bus_index(rec["bus"], f"{lid}.bus")
        mw = _mw(rec["mw"], f"{lid}.mw")
        if rec["kind"] not in LOAD_KINDS:
            raise OverlayError(f"{lid}.kind", "Tipo de carga desconocido.", sorted(LOAD_KINDS))
        _name(rec["name"], f"{lid}.name")
        added_mw += mw
        if _flag(rec.get("in_service", True), f"{lid}.in_service"):
            load[i] += mw
    for rec in overlay.get("generators") or []:
        gid = rec["id"]
        for key in ("bus", "mw", "tech"):
            _require(rec, key, gid)
        i = bus_index(rec["bus"], f"{gid}.bus")
        mw = _mw(rec["mw"], f"{gid}.mw")
        if rec["tech"] not in TECHS:
            raise OverlayError(f"{gid}.tech", "Tecnología desconocida.", sorted(TECHS))
        synchronous = _flag(rec.get("synchronous", rec["tech"] in SYNC_TECH), f"{gid}.synchronous")
        h = _number(
            rec.get("inertia_h", DEFAULT_INERTIA_H), f"{gid}.inertia_h", 0.0, MAX_INERTIA_H, open_lo=True
        )
        added_mw += mw
        if _flag(rec.get("in_service", True), f"{gid}.in_service"):
            gen[i] += mw
            if synchronous:
                sync[i] += mw
                inertia[i] += h * mw

    count = sum(not r.get("removed") for r in added) + sum(
        len(overlay.get(k) or []) for k in ("lines", "loads", "generators")
    )
    if count > MAX_ADDED:
        raise OverlayError("overlay", f"Máximo {MAX_ADDED} elementos agregados por sesión.")
    if added_mw > MAX_ADDED_MW:
        raise OverlayError(
            "overlay", f"Máximo {MAX_ADDED_MW:.0f} MW agregados o cambiados (carga + generación)."
        )

    index = dict(net.index)
    for i in range(n, total):
        index.setdefault(names[i], i)
    edited = ReducedNetwork(
        names=names,
        lat=lat,
        lon=lon,
        kv=kv,
        model_buses=list(net.model_buses) + [[] for _ in added],
        map_nodes=list(net.map_nodes) + [[] for _ in added],
        lines=lines,
        index=index,
        bus_of_model_bus=net.bus_of_model_bus,
    )
    warnings: list[dict[str, Any]] = []
    balance = _rebalance(edited, base, load, gen, sync, in_service, dropped, pinned, warnings)
    edited_point = OperatingPoint(point.id, point.label, load, gen, sync, inertia, people)
    return Applied(edited, edited_point, warnings, balance)


def _rebalance(
    net: ReducedNetwork,
    base: dict[str, np.ndarray],
    load: np.ndarray,
    gen: np.ndarray,
    sync: np.ndarray,
    in_service: list[bool],
    dropped: list[tuple[int, int]],
    pinned: set[int],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Redispatch, per island, the change in generation minus load caused by the edit (in place).

    Out-of-service buses lose their base injection. When a group of them touched a single live
    island through its base lines, that island redispatches the loss; when it touched several, the
    outage split the island and each part keeps its base imbalance. Buses whose generation the
    overlay sets (`pinned`) take no share of the redispatch."""
    connected = {ln.a for ln in net.lines} | {ln.b for ln in net.lines}
    islands = find_islands(net, set())
    island_of = {i: k for k, island in enumerate(islands) for i in island}
    extra = [0.0] * len(islands)
    neighbours: dict[int, set[int]] = {}
    for a, b in dropped:
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)
    seen: set[int] = set()
    for start in (i for i in range(len(in_service)) if not in_service[i]):
        if start in seen:
            continue
        seen.add(start)
        group, stack, touched = [], [start], set()
        while stack:
            i = stack.pop()
            group.append(i)
            for j in neighbours.get(i, ()):
                if in_service[j]:
                    touched.add(island_of[j])
                elif j not in seen:
                    seen.add(j)
                    stack.append(j)
        if len(touched) == 1:
            idx = np.array(group)
            extra[touched.pop()] -= float((base["gen"][idx] - base["load"][idx]).sum())
    balance = []
    for k, island in enumerate(islands):
        if not any(in_service[i] for i in island):
            continue  # out-of-service buses carry nothing; their loss is counted in a live island
        if len(island) == 1 and in_service[island[0]] and island[0] not in connected:
            warnings.append(
                {
                    "code": "isolated_bus",
                    "ids": [bus_id(island[0])],
                    "message": "Barra sin líneas en servicio: queda aislada.",
                }
            )
        idx = np.array(island)
        delta = float((gen[idx] - load[idx]).sum() - (base["gen"][idx] - base["load"][idx]).sum()) + extra[k]
        flagged = False
        if abs(delta) > 1e-9:
            free = np.array([in_service[i] and i not in pinned for i in island])
            weights = np.where(free, base["sync"][idx], 0.0)
            if weights.sum() <= 0:
                warnings.append(_no_sync(island, delta))
                flagged = True
            else:
                share = -delta * weights / weights.sum()
                share = np.maximum(share, -sync[idx])  # a unit cannot go below zero
                gen[idx] += share
                sync[idx] += share
                moved = {bus_id(i): round(float(s), 3) for i, s in zip(island, share, strict=True) if s}
                balance.append(
                    {
                        "buses": moved,
                        "redispatch_mw": round(float(share.sum()), 3),
                        "is_assumption": True,
                        "rule": BALANCE_RULE,
                    }
                )
                if abs(float(share.sum()) + delta) > 1e-6:
                    warnings.append(_no_sync(island, delta + float(share.sum())))
                    flagged = True
        residual = float((gen[idx] - load[idx]).sum())
        if not flagged and abs(residual) >= UNBALANCED_MW:
            warnings.append(
                {
                    "code": "unbalanced_island",
                    "ids": [bus_id(i) for i in island],
                    "message": f"Isla separada con {residual:+.0f} MW de desbalance base: "
                    "el caso base ya muestra una perturbación.",
                }
            )
    return balance


def _no_sync(island: list[int], missing: float) -> dict[str, Any]:
    return {
        "code": "no_sync_to_redispatch",
        "ids": [bus_id(i) for i in island],
        "message": f"Sin generación sincrónica base para redespachar {-missing:+.0f} MW: la isla queda desbalanceada.",
    }


# ------------------------------------------------------------------ helpers


def _copy(overlay: dict[str, Any]) -> dict[str, Any]:
    out = {**empty_overlay(), **copy.deepcopy(overlay)}
    out["seq"] = {**empty_overlay()["seq"], **out["seq"]}
    return out


def _kind(kind: str) -> None:
    if kind not in KINDS:
        raise OverlayError("kind", f"Tipo de elemento desconocido: {kind}.", list(KINDS))


def _known_fields(fields: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise OverlayError(unknown[0], "Campo no permitido.", sorted(allowed))


def _base_ids(kind: str, net: ReducedNetwork) -> set[str]:
    if kind == "bus":
        return {bus_id(i) for i in range(net.size)}
    if kind == "line":
        return {ln.id for ln in net.lines}
    return set()


def _session_record(overlay: dict[str, Any], kind: str, element_id: str) -> dict[str, Any]:
    for rec in overlay[_LIST[kind]]:
        if rec["id"] == element_id and not rec.get("removed"):
            return rec
    raise OverlayError("id", f"Elemento desconocido: {element_id}.", not_found=True)


def _bus_ref(ref: Any, total: int) -> int | None:
    if isinstance(ref, str) and len(ref) == 4 and ref[0] == "B" and ref[1:].isdigit():
        i = int(ref[1:])
        return i if i < total else None
    return None


def _default_x_pu(overlay: dict[str, Any], rec: dict[str, Any], net: ReducedNetwork) -> float:
    """Reactance from the line length and the typical ohm per km of its voltage class."""
    kv = rec.get("kv")
    if not isinstance(kv, int | float) or int(kv) not in X_PER_KM:
        raise OverlayError(
            "x_pu", "Indica x_pu: no hay reactancia típica para esa tensión.", sorted(map(str, X_PER_KM))
        )
    ends = []
    for side in ("a", "b"):
        i = _bus_ref(rec.get(side), net.size + len(overlay["buses"]))
        if i is None:
            raise OverlayError(side, f"Barra desconocida: {rec.get(side)}.", not_found=True)
        if i < net.size:
            ends.append((net.lon[i], net.lat[i]))
        else:
            bus = overlay["buses"][i - net.size]
            ends.append((float(bus.get("lon", 0.0)), float(bus.get("lat", 0.0))))
    km = haversine_km(*ends[0], *ends[1])
    ohm_per_km = sum(X_PER_KM[int(kv)]) / 2
    return max(round(km * ohm_per_km / (float(kv) ** 2 / BASE_MVA), 6), X_MIN_PU)


def _require(rec: dict[str, Any], key: str, where: str) -> None:
    if rec.get(key) is None:
        raise OverlayError(f"{where}.{key}", "Campo obligatorio.")


def _number(value: Any, where: str, lo: float | None, hi: float | None, *, open_lo: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not np.isfinite(value):
        raise OverlayError(where, "Debe ser un número.")
    v = float(value)
    if lo is not None and (v <= lo if open_lo else v < lo):
        raise OverlayError(where, f"Debe ser {'mayor que' if open_lo else 'al menos'} {lo:g}.")
    if hi is not None and v > hi:
        raise OverlayError(where, f"Debe ser como máximo {hi:g}.")
    return v


def _mw(value: Any, where: str) -> float:
    return _number(value, where, 0.0, MAX_ELEMENT_MW, open_lo=True)


def _capacity(value: Any, where: str) -> float:
    return _number(value, where, 0.0, MAX_CAPACITY_MW, open_lo=True)


def _x_pu(value: Any, where: str) -> float:
    return _number(value, where, X_MIN_PU, X_MAX_PU)


def _kv(value: Any, kv_set: list[float], where: str) -> float:
    v = _number(value, where, None, None)
    if v not in kv_set:
        raise OverlayError(where, "Tensión fuera de las de la red base.", [f"{k:g}" for k in kv_set])
    return v


def _flag(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise OverlayError(where, "Debe ser true o false.")
    return value


def _name(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise OverlayError(where, "Nombre obligatorio de hasta 80 caracteres.")
    return value.strip()
