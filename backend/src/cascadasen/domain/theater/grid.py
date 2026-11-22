"""Real grid state of the theatre on the mapa 3 network (docs/strategy.md 3, docs/mapa3.md).

Per bus it keeps the plan (load, synchronous and non-synchronous generation, inertia from the secure
base case of the operating point) and the current state. Physical events and switching run the mapa 3
cascade engine (`run_cascade_state`) from the current state, so dark buses, open lines and flows are
exactly what the viewer would draw. Areas only aggregate buses: reads are by area, writes go through
explicit methods that spread a change over the area's buses.

Area dicts returned by the read properties are read-only views: every write is a method.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import numpy as np

from cascadasen.domain.cascade.engine import CascadeParams, run_cascade_state
from cascadasen.domain.cascade.flow import dc_flow, find_islands
from cascadasen.domain.cascade.frequency import F0
from cascadasen.domain.cascade.frequency import Params as FrequencyParams
from cascadasen.domain.cascade.scenario import OperatingPoint
from cascadasen.domain.theater.areas import EDAC_ZONES, TheaterNetwork, bus_id

RESERVE_SHARE = FrequencyParams().reserve_share_of_sync  # same primary reserve the engine uses
KINDS = ("sync", "renewable")
TECH_KIND = {"solar": "renewable", "eolica": "renewable", "renewable": "renewable"}


@dataclass(frozen=True)
class Change:
    """One physical change applied before a cascade (area, zone, corridor, line or bus level)."""

    kind: str  # open_corridor | lines_out | node_out | trip_gen | group_out | renewable_drop |
    # disable_defense | no_reserve | load_step
    target: str
    mw: float | None = None
    share: float | None = None
    tech: str | None = None
    lines: tuple[str, ...] = ()


class ChangeError(ValueError):
    pass


@dataclass
class TheaterGrid:
    net: TheaterNetwork
    point_id: str
    plan_load: np.ndarray
    plan_sync: np.ndarray
    plan_renew: np.ndarray
    plan_inertia: np.ndarray
    people: np.ndarray
    load: np.ndarray  # served load per bus
    sync: np.ndarray
    renew: np.ndarray
    inertia: np.ndarray
    open_lines: set[str] = field(default_factory=set)
    held_open: set[str] = field(default_factory=set)  # opened by an active effect or islanding
    dark: set[int] = field(default_factory=set)
    disabled: set[str] = field(default_factory=set)  # defence ids "edac:<zone>"
    no_reserve: set[str] = field(default_factory=set)  # areas
    extra_reserve: dict[str, float] = field(default_factory=dict)  # area -> MW of fast reserve (first order)
    battery: dict[str, float] = field(
        default_factory=dict
    )  # area -> MW of batteries (200 ms delay, 300 ms ramp)
    # physical readings of the last transient per area (docs/agents.md 1): frequency after the transient,
    # its nadir and initial RoCoF, and the island verdict. Areas without a transient this cycle sit at f0.
    freq_hz: dict[str, float | None] = field(default_factory=dict)
    nadir_hz: dict[str, float | None] = field(default_factory=dict)
    rocof_hz_s: dict[str, float] = field(default_factory=dict)
    island_result: dict[str, str] = field(default_factory=dict)
    last_islands: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------- build

    @classmethod
    def from_point(cls, net: TheaterNetwork, point: OperatingPoint) -> TheaterGrid:
        sync = point.sync_mw.astype(float).copy()
        renew = np.maximum(point.gen - point.sync_mw, 0.0).astype(float)
        grid = cls(
            net,
            point.id,
            point.load.astype(float).copy(),
            sync.copy(),
            renew.copy(),
            point.inertia_mws.astype(float).copy(),
            point.people.astype(float).copy(),
            point.load.astype(float).copy(),
            sync,
            renew,
            point.inertia_mws.astype(float).copy(),
        )
        grid.settle_frequency()
        return grid

    def copy(self) -> TheaterGrid:
        return copy.deepcopy(self)

    # ------------------------------------------------------------- reads

    def _sum(self, arr: np.ndarray) -> MappingProxyType:
        idx, names = self.net.area_index
        sums = np.bincount(idx, weights=arr, minlength=len(names))
        return MappingProxyType({a: float(sums[k]) for k, a in enumerate(names)})

    @property
    def load_mw(self) -> MappingProxyType:
        """Demand per area (the plan, including demand surges)."""
        return self._sum(self.plan_load)

    @property
    def served_mw(self) -> MappingProxyType:
        return self._sum(self.load)

    @property
    def blackout_areas(self) -> frozenset[str]:
        idx, names = self.net.area_index
        loaded = self.plan_load > 0.5
        dark = np.zeros(len(loaded), dtype=bool)
        if self.dark:
            dark[list(self.dark)] = True
        n_loaded = np.bincount(idx, weights=loaded, minlength=len(names))
        n_lit = np.bincount(idx, weights=loaded & ~dark, minlength=len(names))
        return frozenset(a for k, a in enumerate(names) if n_loaded[k] > 0 and n_lit[k] == 0)

    @property
    def disabled_defenses(self) -> frozenset[str]:
        return frozenset(self.disabled)

    @property
    def no_reserve_areas(self) -> frozenset[str]:
        return frozenset(self.no_reserve)

    def gen(self, area: str) -> float:
        b = list(self.net.areas[area].buses)
        return float(self.sync[b].sum() + self.renew[b].sum())

    def sync_gen(self, area: str) -> float:
        return float(self.sync[list(self.net.areas[area].buses)].sum())

    def tripped(self, area: str, kind: str | None = None) -> float:
        """Generation below plan in the area (what restoration brings back)."""
        b = list(self.net.areas[area].buses)
        s = max(0.0, float(self.plan_sync[b].sum() - self.sync[b].sum()))
        r = max(0.0, float(self.plan_renew[b].sum() - self.renew[b].sum()))
        return {"sync": s, "renewable": r}.get(kind or "", s + r)

    def reserve_mw(self, area: str) -> float:
        if area in self.no_reserve or area in self.blackout_areas:
            return 0.0
        return (
            RESERVE_SHARE * self.sync_gen(area)
            + self.extra_reserve.get(area, 0.0)
            + self.battery.get(area, 0.0)
        )

    def settle_frequency(self) -> None:
        """Between operational cycles secondary control brings energized islands back to f0 (assumption,
        docs/agents.md 1.2); dark areas have no frequency."""
        dark = self.blackout_areas
        for a in self.net.order:
            self.freq_hz[a] = None if a in dark else F0
            self.nadir_hz[a] = None if a in dark else F0
            self.rocof_hz_s[a] = 0.0
            self.island_result[a] = "dark" if a in dark else "maintains"
        self.last_islands = []

    def corridor_closed(self, cid: str) -> bool:
        """At least one line of the corridor is in service."""
        return any(lid not in self.open_lines for lid in self.net.corridors[cid].lines)

    def islands(self) -> list[list[int]]:
        return find_islands(self.net.buses, self.open_lines)

    def island_of_area(self, area: str) -> list[str]:
        mine = set(self.net.areas[area].buses)
        for isl in self.islands():
            if mine & set(isl):
                return sorted({self.net.area_of_bus[b] for b in isl}, key=self.net.order.index)
        return [area]

    def people_without_power(self) -> float:
        served = np.divide(self.load, self.plan_load, out=np.ones_like(self.load), where=self.plan_load > 0)
        return float((self.people * (1.0 - np.clip(served, 0.0, 1.0))).sum())

    # ------------------------------------------------------- engine view

    def operating_point(self) -> OperatingPoint:
        return OperatingPoint(
            self.point_id,
            self.point_id,
            self.load.copy(),
            self.sync + self.renew,
            self.sync.copy(),
            self.inertia.copy(),
            self.people.copy(),
        )

    def extra_reserve_by_bus(self) -> np.ndarray:
        out = np.zeros(self.net.buses.size)
        for a, A in self.net.areas.items():
            b = list(A.buses)
            sync = self.sync[b]
            if a in self.no_reserve:
                out[b] -= RESERVE_SHARE * sync  # remote dispatch lost: the area's reserve does not answer
            mw = self.extra_reserve.get(a, 0.0)
            if mw > 0:
                share = sync / sync.sum() if sync.sum() > 0 else np.full(len(b), 1.0 / len(b))
                out[b] += mw * share
        return out

    def battery_by_bus(self) -> np.ndarray:
        """Battery MW per area spread over the area's loaded buses (batteries sit near demand)."""
        out = np.zeros(self.net.buses.size)
        for a, mw in self.battery.items():
            if mw <= 0:
                continue
            b = list(self.net.areas[a].buses)
            load = self.load[b]
            out[b] += mw * (load / load.sum() if load.sum() > 0 else np.full(len(b), 1.0 / len(b)))
        return out

    def _read_islands(self, islands: list[dict[str, Any]]) -> None:
        """Per-area physics from the engine's settled islands: an area split between islands takes the
        island that holds most of its demand."""
        self.settle_frequency()
        out = []
        weight: dict[str, float] = {}
        for isl in islands:
            buses = isl["bus_idx"]
            areas: dict[str, float] = {}
            for b in buses:
                a = self.net.area_of_bus[b]
                areas[a] = areas.get(a, 0.0) + float(self.plan_load[b])
            entry = {k: v for k, v in isl.items() if k != "bus_idx"}
            entry["areas"] = sorted(areas, key=self.net.order.index)
            out.append(entry)
            for a, w in areas.items():
                if w < weight.get(a, -1.0):
                    continue
                weight[a] = w
                result = isl["result"]
                lost = result in ("dark", "blackout", "local_cut")
                self.island_result[a] = result
                self.freq_hz[a] = None if lost else isl.get("final_hz")
                self.nadir_hz[a] = isl.get("min_hz")
                self.rocof_hz_s[a] = float(isl.get("rocof_hz_s") or 0.0)
        self.last_islands = out

    def run_cascade(self, cut_lines: list[str]) -> dict[str, Any]:
        """Run the mapa 3 cascade engine from the current state and keep its result."""
        cut = [lid for lid in dict.fromkeys(cut_lines) if lid not in self.open_lines]
        timeline, state = run_cascade_state(
            self.net.buses,
            self.operating_point(),
            cut,
            CascadeParams(),
            open_lines=frozenset(self.open_lines),
            edac_off=frozenset(d.split(":", 1)[1] for d in self.disabled if d.split(":", 1)[1] in EDAC_ZONES),
            extra_reserve_by_bus=self.extra_reserve_by_bus(),
            battery_by_bus=self.battery_by_bus(),
        )
        self.load = state.load.astype(float)
        self.sync = np.minimum(state.sync.astype(float), state.gen.astype(float))
        self.renew = np.maximum(state.gen - self.sync, 0.0).astype(float)
        self.inertia = state.inertia.astype(float)
        self.open_lines = set(state.open_lines)
        self.dark |= set(state.dark)
        self._read_islands(state.islands)
        return timeline

    def frame(self) -> dict[str, Any]:
        """Quasi-steady state in the mapa 3 `Frame` format, plus served load per bus."""
        islands = self.islands()
        flows = dc_flow(self.net.buses, self.open_lines, self.sync + self.renew - self.load, islands)
        edges = {}
        for f, ln in zip(flows, self.net.buses.lines, strict=True):
            ratio = abs(f) / ln.capacity_mw if ln.capacity_mw > 0 else 0.0
            status = "open" if ln.id in self.open_lines else ("overload" if ratio > 1.0 else "ok")
            if status != "ok" or abs(f) >= 5:
                edges[ln.id] = {"flow_mw": round(float(f)), "status": status, "loading": round(ratio, 3)}
        return {
            "edges": edges,
            "dark": sorted(bus_id(b) for b in self.dark),
            "islands": [
                {
                    "buses": len(i),
                    "gen_mw": round(float((self.sync[i] + self.renew[i]).sum())),
                    "load_mw": round(float(self.load[i].sum())),
                }
                for i in islands
                if len(i) > 1
            ],
            "buses": {
                bus_id(b): round(float(self.load[b]), 1)
                for b in range(self.net.buses.size)
                if self.plan_load[b] > 0
            },
        }

    # ------------------------------------------------------------ writes

    def apply(self, ch: Change) -> tuple[list[str], dict[str, Any]]:
        """Apply one change; returns (lines to cut in the cascade, event params)."""
        net = self.net
        if ch.kind == "open_corridor":
            lines = list(net.corridors[ch.target].lines)
            self.held_open |= set(lines)
            return lines, {}
        if ch.kind == "lines_out":
            self.held_open |= set(ch.lines)
            return list(ch.lines), {}
        if ch.kind == "node_out":
            bus = int(ch.target[1:])
            lines = net.bus_lines(bus)
            self.held_open |= set(lines)
            return lines, {"bus": ch.target}
        if ch.kind in ("trip_gen", "group_out", "renewable_drop"):
            areas = net.zone_areas(ch.target) or [ch.target]
            if ch.kind == "trip_gen":  # no technology given: both kinds in proportion
                kind = TECH_KIND.get(ch.tech, "sync") if ch.tech else None
            else:
                kind = TECH_KIND.get(ch.tech or "solar", "renewable")
            tripped = 0.0
            for a in areas:
                online = self._online(a, kind)
                mw = ch.mw / len(areas) if ch.mw is not None else (ch.share or 0.25) * online
                tripped += self.trip(a, mw, kind)
            return [], {"mw": round(tripped, 1)}
        if ch.kind == "disable_defense":
            self.disabled.add(ch.target)
            return [], {}
        if ch.kind == "no_reserve":
            self.no_reserve.add(ch.target)
            return [], {}
        if ch.kind == "load_step":
            areas = net.zone_areas(ch.target) or [ch.target]
            added = 0.0
            for a in areas:
                mw = ch.mw / len(areas) if ch.mw is not None else (ch.share or 0.05) * self.load_mw[a]
                added += self.add_load(a, mw)
            return [], {"mw": round(added, 1)}
        raise ChangeError(f"tipo de cambio desconocido: {ch.kind}")

    def _online(self, area: str, kind: str | None) -> float:
        b = list(self.net.areas[area].buses)
        if kind == "sync":
            return float(self.sync[b].sum())
        if kind == "renewable":
            return float(self.renew[b].sum())
        return float(self.sync[b].sum() + self.renew[b].sum())

    def trip(self, area: str, mw: float, kind: str | None) -> float:
        """Disconnect `mw` of generation in the area, spread over its buses (inertia goes with it)."""
        kinds = [kind] if kind else list(KINDS)
        total = sum(self._online(area, k) for k in kinds)
        if total <= 0 or mw <= 0:
            return 0.0
        mw = min(mw, total)
        b = np.array(self.net.areas[area].buses)
        for k in kinds:
            arr = self.sync if k == "sync" else self.renew
            part = mw * self._online(area, k) / total
            cur = arr[b]
            if cur.sum() <= 0:
                continue
            new = cur * (1.0 - part / cur.sum())
            if k == "sync":
                ratio = np.divide(new, cur, out=np.zeros_like(cur), where=cur > 0)
                self.inertia[b] *= ratio
            arr[b] = new
        return mw

    def add_load(self, area: str, mw: float) -> float:
        b = np.array([i for i in self.net.areas[area].buses if i not in self.dark])
        if mw <= 0 or len(b) == 0:
            return 0.0
        base = self.plan_load[b]
        share = base / base.sum() if base.sum() > 0 else np.full(len(b), 1.0 / len(b))
        self.plan_load[b] += mw * share
        self.load[b] += mw * share
        return mw

    def reduce_load(self, area: str, mw: float) -> float:
        b = np.array(self.net.areas[area].buses)
        cur = self.load[b]
        mw = min(mw, float(cur.sum()))
        if mw <= 0:
            return 0.0
        self.load[b] = cur * (1.0 - mw / cur.sum())
        self.rebalance(area)
        return mw

    def rebalance(self, area: str) -> None:
        """Keep the area's island balanced by moving synchronous dispatch (quasi-steady state)."""
        isl = next((i for i in self.islands() if set(i) & set(self.net.areas[area].buses)), None)
        if not isl:
            return
        b = np.array(isl)
        gap = float(self.load[b].sum() - self.sync[b].sum() - self.renew[b].sum())
        if abs(gap) < 0.5:
            return
        sync = self.sync[b]
        if gap > 0:  # raise synchronous units up to their plan
            room = np.maximum(self.plan_sync[b] - sync, 0.0)
            if room.sum() > 0:
                sync = sync + room * min(1.0, gap / room.sum())
        elif sync.sum() > 0:
            sync = sync * max(0.0, 1.0 + gap / sync.sum())
        self.sync[b] = sync

    def reclose(self, lines: list[str]) -> list[str]:
        back = [lid for lid in lines if lid in self.open_lines]
        self.open_lines -= set(back)
        self.held_open -= set(back)
        return back

    def restore_step(self, area: str, share: float, gen_share: float | None = None) -> tuple[float, bool]:
        """One cycle of operational restoration: energize the area's buses, bring generation back toward
        the plan and pick up load up to the island's headroom. Returns (MW picked up, done)."""
        A = self.net.areas[area]
        b = np.array(A.buses)
        self.dark -= set(A.buses)
        for arr, plan in ((self.sync, self.plan_sync), (self.renew, self.plan_renew)):
            gap = np.maximum(plan[b] - arr[b], 0.0)
            arr[b] += gap * min(1.0, gen_share if gen_share is not None else share)
        ratio = np.divide(self.sync[b], self.plan_sync[b], out=np.ones(len(b)), where=self.plan_sync[b] > 0)
        self.inertia[b] = self.plan_inertia[b] * np.clip(ratio, 0.0, 1.0)
        isl = next((i for i in self.islands() if set(i) & set(A.buses)), list(A.buses))
        ib = np.array(isl)
        headroom = float(self.sync[ib].sum() + self.renew[ib].sum() - self.load[ib].sum())
        headroom += float(np.maximum(self.plan_sync[ib] - self.sync[ib], 0.0).sum())
        want = np.maximum(self.plan_load[b] - self.load[b], 0.0)
        step = min(float(want.sum()), share * float(self.plan_load[b].sum()), max(0.0, headroom))
        if want.sum() > 0 and step > 0:
            self.load[b] += want * (step / want.sum())
        self.rebalance(area)
        done = (
            float(np.maximum(self.plan_load[b] - self.load[b], 0.0).sum()) <= 1.0
            and self.tripped(area) <= 1.0
        )
        return step, done
