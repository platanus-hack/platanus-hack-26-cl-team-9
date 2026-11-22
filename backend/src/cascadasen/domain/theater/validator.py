"""Deterministic validator of courses of action (docs/strategy.md section 7).

It checks, in order: the action exists and the target is valid; the proposer's role may propose it;
it is not already active; resources fit (keeping the commander's reserve); it is physically
feasible on the real state; and it respects the mission. It reads the real state, but tells the
proposer only what it could observe (`observable_code`). No agent can bypass it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import ACTIONS, Role
from cascadasen.domain.theater.config import Mission
from cascadasen.domain.theater.decisions import COA, Intent, Verdict
from cascadasen.domain.theater.grid import Change
from cascadasen.domain.theater.resources import Ledger
from cascadasen.domain.theater.state import RealState

PERSISTENT = frozenset(
    {"manual_operation", "backup_comms", "digital_segmentation", "fast_reserve", "battery_support"}
)
HIDDEN = {"unsafe_separation": "stability_check_failed"}


@dataclass
class ValidationContext:
    network: TheaterNetwork
    real: RealState
    ledger: Ledger
    mission: Mission
    intent: Intent | None
    action_params: dict[str, dict]
    defense_areas: dict[str, list[str]]
    active: set[str] = field(default_factory=set)
    check_resources: bool = True
    check_physics: bool = True


def costs_of(coa: COA, params: dict[str, dict]) -> dict[str, float]:
    return {k: float(v) for k, v in (params.get(coa.action, {}).get("costs") or {}).items()}


def _verdict(ok: bool, code: str, *side: str) -> Verdict:
    return Verdict(ok, code, HIDDEN.get(code, code), tuple(side))


def _target_ok(coa: COA, ctx: ValidationContext) -> bool:
    net = ctx.network
    if coa.action == "restore_element":
        return coa.target in net.areas or coa.target in net.corridors
    kind = ACTIONS[coa.action].target
    if kind == "area":
        return coa.target in net.areas
    if kind == "corridor":
        return coa.target in net.corridors
    return coa.target in ctx.defense_areas


def _command_path(area: str, ctx: ValidationContext) -> str | None:
    d = ctx.real.digital[area]
    if d.manual_ops:
        return None
    if d.segmented:
        return "area_segmented"
    if d.comms == "down" or not d.remote_control:
        return "remote_command_not_acknowledged"
    return None


def validate(coa: COA, ctx: ValidationContext) -> Verdict:
    spec = ACTIONS.get(coa.action)
    if spec is None or not _target_ok(coa, ctx):
        return _verdict(False, "unknown_action_or_target")
    if Role(coa.proposer) not in spec.proposers:
        return _verdict(False, "not_permitted")
    if coa.action in PERSISTENT and coa.key in ctx.active:
        return _verdict(False, "already_active")
    keep = ctx.intent.reserve_keep if ctx.intent and spec.weight != "restore" else 0.0
    if ctx.check_resources and not ctx.ledger.can_afford(costs_of(coa, ctx.action_params), keep):
        return _verdict(False, "insufficient_resources")
    return _feasible(coa, ctx)


def _feasible(coa: COA, ctx: ValidationContext) -> Verdict:
    real, net, a = ctx.real, ctx.network, coa.target
    grid = real.grid
    spec = ACTIONS[coa.action]
    area = a if a in net.areas else None
    if coa.action == "rearm_defense":
        area = next(iter(ctx.defense_areas.get(a, [])), None)
    if spec.remote_dependent and area and coa.action != "restore_element":
        blocked = _command_path(area, ctx)
        if blocked:
            return _verdict(False, blocked)

    if coa.action == "backup_comms":
        d = real.digital[a]
        return (
            _verdict(True, "ok", "kit_committed")
            if d.comms != "primary"
            else _verdict(True, "ok", "no_effect")
        )
    if coa.action == "manual_operation":
        return (
            _verdict(False, "already_active")
            if real.digital[a].manual_ops
            else _verdict(True, "ok", "crew_committed")
        )
    if coa.action == "digital_segmentation":
        if real.digital[a].segmented:
            return _verdict(False, "already_active")
        side = () if real.digital[a].manual_ops else ("observability_reduced",)
        return _verdict(True, "ok", *side)
    if coa.action == "preventive_load_reduction":
        if a in grid.blackout_areas or grid.served_mw[a] <= 1:
            return _verdict(False, "area_deenergized")
        if a in ctx.mission.priority_areas and not (ctx.intent and ctx.intent.allow_priority_shedding):
            return _verdict(False, "mission_constraint")
        return _verdict(True, "ok", "load_reduced")
    if coa.action in ("fast_reserve", "battery_support"):
        return _verdict(False, "area_deenergized") if a in grid.blackout_areas else _verdict(True, "ok")
    if coa.action == "rearm_defense":
        return _verdict(True, "ok") if a in grid.disabled_defenses else _verdict(True, "ok", "no_effect")
    if coa.action == "islanding_prep":
        return _islanding(coa, ctx)
    if coa.action == "restore_element":
        return _restore(coa, ctx)
    if coa.action == "request_external_support":
        return _verdict(True, "ok") if not real.digital[a].external_ok else _verdict(True, "ok", "no_effect")
    return _verdict(True, "ok")  # isr_tasking, field_verification


def _islanding(coa: COA, ctx: ValidationContext) -> Verdict:
    grid = ctx.real.grid
    if not grid.corridor_closed(coa.target):
        return _verdict(False, "already_open")
    if not ctx.check_physics:
        return _verdict(True, "ok", "controlled_separation")
    trial = grid.copy()  # the mapa 3 cascade engine on a copy of the real state
    trial.apply(Change("open_corridor", coa.target))
    summary = trial.run_cascade(list(ctx.network.corridors[coa.target].lines))["summary"]
    if any(i["result"] == "blackout" for i in summary["islands"]) or summary["load_shed_mw"] > 0.5:
        return _verdict(False, "unsafe_separation")
    return _verdict(True, "ok", "controlled_separation")


def restorable(area: str, ctx_real: RealState) -> bool:
    g = ctx_real.grid
    return area in g.blackout_areas or g.served_mw[area] < g.load_mw[area] - 1.0 or g.tripped(area) > 1.0


def _restore(coa: COA, ctx: ValidationContext) -> Verdict:
    real, net, grid = ctx.real, ctx.network, ctx.real.grid
    if coa.target in net.corridors:
        c = net.corridors[coa.target]
        if not any(lid in grid.open_lines for lid in c.lines):
            return _verdict(False, "nothing_to_restore")
        if c.a in grid.blackout_areas and c.b in grid.blackout_areas:
            return _verdict(False, "no_restoration_path")
        return _verdict(True, "ok", "crew_committed")
    a = coa.target
    if not restorable(a, real):
        return _verdict(False, "nothing_to_restore")
    blocked = _command_path(a, ctx)
    if blocked:
        return _verdict(False, blocked)
    if a in grid.blackout_areas:
        own_sync = grid.tripped(a, "sync")
        neighbour = any(
            (c.a if c.b == a else c.b) not in grid.blackout_areas and grid.corridor_closed(c.id)
            for c in net.incident(a)
        )
        if own_sync <= 1.0 and not neighbour:
            return _verdict(False, "no_restoration_path")
    return _verdict(True, "ok", "crew_committed")
