"""Execution engine: applies abstract events and approved actions to the real state.

Events (docs/strategy.md section 6) change supervision (digital) or the grid (physical, through
one cascade transient per cycle). Effects persist until a defensive action clears them, unless
they have a duration. Clearing rules:

    D1 telemetry loss       mitigated by backup comms; cleared by restoring the area
    D2 telemetry delay      expires; cleared by restoring the area
    D3 unreliable data      cleared after the area stays segmented `clears_after` cycles
    D4 comms loss           mitigated by backup comms; cleared by restoring the area
    D5 false alarms         expires; cleared by segmentation
    D6 external dependency  supervision degrades after `lag` cycles; cleared by external support
    C1/C2/E2 generation     restored progressively by restoring the area
    C3 transmission opening cleared by restoring the corridor (or the area for a substation)
    C4 defence not acting   cleared by re-arming the defence
    C5 remote dispatch loss compensated by manual operation; cleared by segmentation or restoration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.simulation.consequence import consequence_level
from cascadasen.domain.simulation.defenses import DefenseSet
from cascadasen.domain.simulation.engine import Change, ChangeError, TransientResult, run_transient
from cascadasen.domain.simulation.grid import GridState, Physics
from cascadasen.domain.simulation.network import ReducedNetwork, UnknownTargetError
from cascadasen.domain.simulation.powerflow import islands
from cascadasen.domain.theater.catalog import EVENTS
from cascadasen.domain.theater.config import TheaterConfig
from cascadasen.domain.theater.decisions import COA, FieldReport
from cascadasen.domain.theater.state import AreaDigital, Effect, RealState

LEVELS = ("L0", "L1", "L2", "L3")
RESTORABLE_EFFECTS = {
    "C1_generation_loss",
    "C2_common_mode_loss",
    "E2_renewable_drop",
    "C3_transmission_opening",
    "D1_telemetry_loss",
    "D2_telemetry_delay",
    "D4_comms_loss",
    "C5_remote_dispatch_loss",
}
SEGMENTATION_CLEARS = {"D3_unreliable_data", "D5_false_alarms", "C5_remote_dispatch_loss"}


class EventError(ValueError):
    """An event request cannot be applied (unknown type, target or parameters)."""


class UnknownEventTargetError(EventError):
    """The event's target is not an element of the network (HTTP 404)."""


@dataclass(frozen=True)
class EventRequest:
    type: str
    target: str
    params: tuple[tuple[str, Any], ...] = ()
    source: str = "user"
    cause: str = "intentional"

    def param(self, name: str, default: Any = None) -> Any:
        return dict(self.params).get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "params": dict(self.params),
            "source": self.source,
            "cause": self.cause,
        }


@dataclass
class Restoration:
    key: str
    target: str
    started: int
    ready: int


@dataclass
class ExecutionState:
    """Operational bookkeeping that lives next to the real state."""

    active: dict[str, COA] = field(default_factory=dict)  # persistent actions by key
    segmented_since: dict[str, int] = field(default_factory=dict)
    restorations: list[Restoration] = field(default_factory=list)
    pending_reports: list[FieldReport] = field(default_factory=list)
    pending_support: dict[str, int] = field(default_factory=dict)
    released: list[str] = field(default_factory=list)


def refresh_comms(d: AreaDigital, primary_ok: bool | None = None, backup: bool | None = None) -> None:
    if primary_ok is not None:
        d.primary_ok = primary_ok
    if backup is not None:
        d.backup_active = backup
    d.comms = "primary" if d.primary_ok else ("backup" if d.backup_active else "down")


class Executor:
    def __init__(
        self,
        network: ReducedNetwork,
        physics: Physics,
        defenses: DefenseSet,
        cfg: TheaterConfig,
        defense_areas: dict[str, list[str]],
    ) -> None:
        self.net, self.physics, self.defenses, self.cfg = network, physics, defenses, cfg
        self.defense_areas = defense_areas

    # ------------------------------------------------------------ resolution

    def resolve(self, req: EventRequest) -> tuple[str, str | None]:
        """(resolved target, area or None) for an event request; raises EventError."""
        spec = EVENTS.get(req.type)
        if spec is None:
            raise EventError(f"tipo de evento desconocido: {req.type}")
        if "defense" in spec.targets:
            if req.target not in self.defense_areas:
                raise UnknownEventTargetError(f"{req.target}: defensa desconocida")
            return req.target, None
        if "zone" in spec.targets and req.target in self.net.zones:
            return req.target, None
        try:
            r = self.net.resolve(req.target)
        except UnknownTargetError as exc:
            raise UnknownEventTargetError(f"{req.target}: objetivo desconocido") from exc
        if r.kind not in spec.targets and not (r.kind == "line" and "line" in spec.targets):
            if r.area and "area" in spec.targets:
                return r.area, r.area
            raise EventError(f"{req.target}: objetivo no válido para {req.type}")
        if r.kind == "node" and spec.family != "physical":
            return r.area, r.area  # digital effects act on the operating area
        return r.id, r.area

    # ---------------------------------------------------------------- events

    def apply_events(self, real: RealState, reqs: list[tuple[EventRequest, str]]) -> list[tuple[Effect, str]]:
        """Apply this cycle's events. Physical ones share one transient. Returns (effect, note)."""
        out: list[tuple[Effect, str]] = []
        changes: list[Change] = []
        for req, effect_id in reqs:
            target, area = self.resolve(req)
            spec = EVENTS[req.type]
            params = {**(self.cfg.effects.get(req.type) or {}), **dict(req.params)}
            duration = params.get("duration")
            eff = Effect(
                effect_id,
                req.type,
                target,
                area,
                params,
                req.source,
                req.cause,
                real.cycle,
                expires=real.cycle + int(duration) if duration else None,
            )
            if (
                spec.family == "digital"
                and area
                and real.digital[area].segmented
                and req.source == "adversary"
            ):
                eff.established = False
                out.append((eff, "blocked_by_segmentation"))
                real.effects.append(eff)
                continue
            if spec.family == "digital":
                self._digital(real, eff)
            else:
                changes += self._physical_changes(real, eff)
            real.effects.append(eff)
            out.append((eff, "established"))
        if changes:
            self.transient(real, changes)
        return out

    def _digital(self, real: RealState, eff: Effect) -> None:
        d = real.digital[eff.area]
        p = eff.params
        if eff.event == "D1_telemetry_loss":
            d.telemetry = max(0.0, 1.0 - float(p.get("share", 1.0)))
            if d.backup_active:
                d.telemetry = max(d.telemetry, self.cfg.digital["backup_comms_telemetry"])
        elif eff.event == "D2_telemetry_delay":
            d.delay = max(d.delay, int(p.get("cycles", 2)))
        elif eff.event == "D3_unreliable_data":
            d.reliable = False
            d.bias = float(p.get("bias", 0.12))
            d.frozen_served = real.grid.served_mw[eff.area]
        elif eff.event == "D4_comms_loss":
            refresh_comms(d, primary_ok=False)
        elif eff.event == "D5_false_alarms":
            d.false_alarm_rate += float(p.get("rate", 1.5))
        elif eff.event == "D6_external_dependency_loss":
            d.external_ok = False

    def _physical_changes(self, real: RealState, eff: Effect) -> list[Change]:
        p, t = eff.params, eff.target
        if eff.event == "C1_generation_loss":
            return [Change("trip_gen", t, mw=p.get("mw"), share=p.get("share"), tech=p.get("tech"))]
        if eff.event in ("C2_common_mode_loss", "E2_renewable_drop"):
            kind = "group_out" if eff.event == "C2_common_mode_loss" else "renewable_drop"
            return [Change(kind, t, share=float(p.get("share", 0.4)), tech=p.get("tech", "solar"))]
        if eff.event == "C3_transmission_opening":
            r = self.net.resolve(t)
            if r.kind == "corridor":
                return [Change("open_corridor", r.id)]
            if r.kind == "line" and r.corridor:
                return [Change("lines_out", r.corridor, lines=(r.id,))]
            node = r.id if r.kind == "node" else self.net.areas[r.area].main_node
            return [Change("node_out", node)] if node else []
        if eff.event == "C4_defense_not_acting":
            return [Change("disable_defense", t)]
        if eff.event == "C5_remote_dispatch_loss":
            real.digital[eff.area].remote_control = False
            return [Change("no_reserve", eff.area)]
        if eff.event == "E1_demand_surge":
            return [Change("load_step", t, mw=p.get("mw"), share=p.get("share"))]
        return []

    def transient(self, real: RealState, changes: list[Change]) -> TransientResult:
        try:
            res = run_transient(self.net, real.grid, changes, self.defenses, self.physics, full=False)
        except ChangeError as exc:
            raise EventError(str(exc)) from exc
        real.grid = res.state
        level, uncertain = consequence_level(res.islands, res.load_lost_mw)
        real.last_transient = {
            "cycle": real.cycle,
            "level": level,
            "uncertain": uncertain,
            "load_lost_mw": res.load_lost_mw,
            "load_shed_mw": res.load_shed_mw,
            "people_without_power": res.people_without_power,
            "islands": [i.summary() for i in res.islands],
            "events": [
                {"t": e["t"], "type": e["type"], "text_key": e["text_key"], "ids": e["ids"]}
                for e in res.events
            ],
        }
        if LEVELS.index(level) > LEVELS.index(real.worst_level):
            real.worst_level = level
        return res

    # --------------------------------------------------------------- actions

    def apply_action(self, real: RealState, ex: ExecutionState, coa: COA) -> str:
        """Carry out an approved, validated action. Returns an observable outcome code."""
        a, cyc, act = coa.target, real.cycle, self.cfg.actions.get(coa.action, {})
        if coa.action == "isr_tasking":
            real.digital[a].tasked_until = cyc + int(act.get("duration", 3))
        elif coa.action == "field_verification":
            ex.pending_reports.append(self._field_report(real, a))
        elif coa.action == "manual_operation":
            real.digital[a].manual_ops = True
            real.grid.no_reserve_areas.discard(a)
            ex.active[coa.key] = coa
        elif coa.action == "backup_comms":
            d = real.digital[a]
            refresh_comms(d, backup=True)
            if any(e.event == "D1_telemetry_loss" for e in real.active_effects(a)):
                d.telemetry = max(d.telemetry, self.cfg.digital["backup_comms_telemetry"])
            ex.active[coa.key] = coa
        elif coa.action == "digital_segmentation":
            real.digital[a].segmented = True
            ex.segmented_since[a] = cyc
            ex.active[coa.key] = coa
        elif coa.action == "preventive_load_reduction":
            self._reduce_load(real.grid, a, float(act.get("share", 0.05)) * real.grid.load_mw[a])
        elif coa.action == "fast_reserve":
            real.grid.reserve_extra_mw[a] = real.grid.reserve_extra_mw.get(a, 0.0) + float(act.get("mw", 100))
            ex.active[coa.key] = coa
        elif coa.action == "battery_support":
            real.grid.battery_mw[a] = real.grid.battery_mw.get(a, 0.0) + float(act.get("mw", 100))
            ex.active[coa.key] = coa
        elif coa.action == "rearm_defense":
            real.grid.disabled_defenses.discard(a)
            self._clear(real, lambda e: e.event == "C4_defense_not_acting" and e.target == a)
        elif coa.action == "islanding_prep":
            self.transient(real, [Change("open_corridor", a)])
        elif coa.action == "restore_element":
            ex.restorations.append(Restoration(coa.key, a, cyc, cyc + int(act.get("duration", 2))))
        elif coa.action == "request_external_support":
            ex.pending_support[a] = cyc + int(act.get("duration", 3))
        return "executed"

    def _field_report(self, real: RealState, area: str) -> FieldReport:
        effects = real.active_effects(area)
        g = real.grid
        physical = (
            area in g.blackout_areas
            or g.served_mw[area] < g.load_mw[area] - 1
            or bool(sum(g.tripped_mw.get(area, {}).values()) > 1)
        )
        kinds = sorted({EVENTS[e.event].family for e in effects})
        return FieldReport(
            real.cycle + 1,
            area,
            any(EVENTS[e.event].family == "digital" for e in effects)
            or not real.digital[area].remote_control,
            physical,
            tuple(kinds),
        )

    def _clear(self, real: RealState, pred) -> list[Effect]:
        cleared = []
        for e in real.effects:
            if e.active(real.cycle) and pred(e):
                e.cleared = real.cycle
                cleared.append(e)
                self._revert(real, e)
        return cleared

    def _revert(self, real: RealState, e: Effect) -> None:
        if not e.area:
            return
        d = real.digital[e.area]
        others = [x for x in real.active_effects(e.area) if x is not e]
        if e.event == "D1_telemetry_loss" and not any(x.event == "D1_telemetry_loss" for x in others):
            d.telemetry = 1.0
        elif e.event == "D2_telemetry_delay" and not any(x.event == "D2_telemetry_delay" for x in others):
            d.delay = 0
        elif e.event == "D3_unreliable_data" and not any(x.event == "D3_unreliable_data" for x in others):
            d.reliable, d.bias, d.frozen_served = True, 0.0, None
        elif e.event == "D4_comms_loss" and not any(x.event in ("D4_comms_loss",) for x in others):
            refresh_comms(d, primary_ok=d.external_ok)
        elif e.event == "D5_false_alarms":
            d.false_alarm_rate = max(0.0, d.false_alarm_rate - float(e.params.get("rate", 1.5)))
        elif e.event == "D6_external_dependency_loss" and not any(x.event == e.event for x in others):
            d.external_ok = True
            if not any(x.event == "D4_comms_loss" for x in others):
                refresh_comms(d, primary_ok=True)
        elif e.event == "C5_remote_dispatch_loss" and not any(x.event == e.event for x in others):
            d.remote_control = True
            real.grid.no_reserve_areas.discard(e.area)

    def _reduce_load(self, g: GridState, area: str, mw: float) -> None:
        mw = min(mw, g.served_mw[area])
        g.served_mw[area] -= mw
        self._rebalance(g, [area], -mw)

    def _rebalance(self, g: GridState, areas: list[str], delta_load: float) -> None:
        """Keep the island balanced after a load change by moving synchronous dispatch."""
        island = self._island_of(g, areas[0])
        sync = {a: g.sync_gen(a) for a in island}
        total = sum(sync.values())
        if total <= 0:
            return
        for a in island:
            for t in g.gen_mw[a]:
                if t in g.sync_techs and sync[a] > 0:
                    g.gen_mw[a][t] = max(0.0, g.gen_mw[a][t] + delta_load * g.gen_mw[a][t] / total)

    def _island_of(self, g: GridState, area: str) -> list[str]:
        return next((isl for isl in islands(self.net, g) if area in isl), [area])

    # ------------------------------------------------------------ per cycle

    def tick(self, real: RealState, ex: ExecutionState) -> list[dict[str, Any]]:
        """Expire effects, advance segmentation, external support and restorations. Returns notes."""
        notes: list[dict[str, Any]] = []
        cyc = real.cycle
        for e in real.effects:
            if e.established and e.cleared is None and e.expires is not None and cyc >= e.expires:
                e.cleared = e.expires
                self._revert(real, e)
                notes.append({"kind": "effect_expired", "effect": e.id})
            if (
                e.event == "D6_external_dependency_loss"
                and e.active(cyc)
                and cyc - e.start >= int(e.params.get("lag", 2))
            ):
                refresh_comms(real.digital[e.area], primary_ok=False)
        clears_after = int(self.cfg.actions.get("digital_segmentation", {}).get("clears_after", 2))
        for a, since in list(ex.segmented_since.items()):
            if cyc - since >= clears_after:
                cleared = self._clear(real, lambda e, a=a: e.area == a and e.event in SEGMENTATION_CLEARS)
                real.digital[a].segmented = False
                del ex.segmented_since[a]
                ex.active.pop(f"digital_segmentation:{a}", None)
                ex.released.append(f"digital_segmentation:{a}")
                notes.append({"kind": "segmentation_lifted", "area": a, "cleared": [e.id for e in cleared]})
        for a, due in list(ex.pending_support.items()):
            if cyc >= due:
                cleared = self._clear(
                    real, lambda e, a=a: e.area == a and e.event == "D6_external_dependency_loss"
                )
                del ex.pending_support[a]
                notes.append(
                    {"kind": "external_support_arrived", "area": a, "cleared": [e.id for e in cleared]}
                )
        notes += self._restore(real, ex)
        self._auto_release(real, ex)
        for a in self.net.order:
            used = real.grid.reserve_used_mw.get(a, 0.0)
            real.grid.reserve_used_mw[a] = used * (1 - self.cfg.restoration["reserve_recovery"])
        return notes

    def _restore(self, real: RealState, ex: ExecutionState) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        for r in list(ex.restorations):
            if r.target in self.net.corridors:
                finished, note = self._restore_corridor(real, r)
            else:
                finished, note = self._restore_area(real, r)
            if note:
                notes.append(note)
            if finished:
                ex.restorations.remove(r)
                ex.released.append(r.key)
        return notes

    def _restore_corridor(self, real: RealState, r: Restoration) -> tuple[bool, dict[str, Any] | None]:
        if real.cycle < r.ready:
            return False, None
        g = real.grid
        g.open_corridors.discard(r.target)
        g.out_lines -= set(self.net.corridors[r.target].members)
        self._clear(real, lambda e, t=r.target: e.event == "C3_transmission_opening" and e.target == t)
        return True, {"kind": "corridor_restored", "corridor": r.target}

    def _restore_area(self, real: RealState, r: Restoration) -> tuple[bool, dict[str, Any] | None]:
        """Crews arrive the cycle after the decision, clear the area's restorable effects, then bring
        back generation and load a share per cycle (slower under manual operation)."""
        g, rest, a = real.grid, self.cfg.restoration, r.target
        d = real.digital[a]
        if real.cycle < r.started + 1:
            return False, None
        if real.cycle == r.started + 1:
            self._clear(real, lambda e: e.area == a and e.event in RESTORABLE_EFFECTS)
            for nid in [n for n in g.out_nodes if self.net.nodes[n].area == a]:
                g.out_nodes.discard(nid)
                g.out_lines -= set(self.net.nodes[nid].corridor_lines)
        if not d.manual_ops and (d.segmented or d.comms == "down" or not d.remote_control):
            return False, {"kind": "restoration_blocked", "area": a}
        speed = rest["manual_slowdown"] if d.manual_ops else 1.0
        g.blackout_areas.discard(a)
        for t, mw in list(g.tripped_mw.get(a, {}).items()):
            back = mw * rest["gen_share_per_cycle"] * speed if mw > 1 else mw
            g.tripped_mw[a][t] = mw - back
            g.gen_mw[a][t] = g.gen_mw[a].get(t, 0.0) + back
            g.add_inertia(a, t, back)
        island = self._island_of(g, a)
        headroom = sum(g.reserve_mw(x) for x in island) + sum(g.gen(x) - g.served_mw[x] for x in island)
        want = max(0.0, g.load_mw[a] - g.served_mw[a])
        step = min(want, rest["load_share_per_cycle"] * speed * g.load_mw[a], max(0.0, headroom))
        g.served_mw[a] += step
        self._settle(g, island)
        done = g.served_mw[a] >= g.load_mw[a] - 1.0 and sum(g.tripped_mw.get(a, {}).values()) <= 1.0
        note = {"kind": "restoration_progress", "area": a, "restored_mw": round(step, 1), "done": done}
        return done or real.cycle - r.started > 12, note

    def _settle(self, g: GridState, island: list[str]) -> None:
        residual = sum(g.served_mw[x] for x in island) - sum(g.gen(x) for x in island)
        if abs(residual) > 0.5:
            self._rebalance(g, island, residual)

    def _auto_release(self, real: RealState, ex: ExecutionState) -> None:
        """Free crews and kits once an area's supervision and control are healthy again."""
        for key, coa in list(ex.active.items()):
            if coa.action not in ("manual_operation", "backup_comms"):
                continue
            d = real.digital[coa.target]
            healthy = d.primary_ok and d.remote_control and d.telemetry >= 1.0 and d.reliable
            if healthy:
                if coa.action == "manual_operation":
                    d.manual_ops = False
                else:
                    refresh_comms(d, backup=False)
                del ex.active[key]
                ex.released.append(key)
