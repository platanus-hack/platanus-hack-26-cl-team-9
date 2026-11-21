"""Roles, abstract events and defensive courses of action (docs/strategy.md sections 5 and 6).

Events are defined by their effect at operating-area or function level (cyber.md section 8). They
carry no technique: "telemetry lost in A06" says what supervision stops seeing, not why.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    C2 = "c2"
    ISR = "isr"
    OPS = "operations"
    STAB = "stabilization"
    LOG = "logistics"
    AUDITOR = "auditor"
    ADVERSARY = "adversary"


DEFENDERS = (Role.C2, Role.ISR, Role.OPS, Role.STAB, Role.LOG, Role.AUDITOR)


@dataclass(frozen=True)
class EventSpec:
    id: str
    family: str  # physical | digital | external
    cyber_class: str | None
    targets: tuple[str, ...]  # accepted target kinds: area, node, corridor, line, zone, defense
    label_key: str


EVENTS: dict[str, EventSpec] = {
    e.id: e
    for e in (
        EventSpec("C1_generation_loss", "physical", "C1", ("area", "node"), "ev_generation_loss"),
        EventSpec("C2_common_mode_loss", "physical", "C2", ("zone",), "ev_common_mode_loss"),
        EventSpec(
            "C3_transmission_opening",
            "physical",
            "C3",
            ("corridor", "node", "area", "line"),
            "ev_transmission_opening",
        ),
        EventSpec("C4_defense_not_acting", "physical", "C4", ("defense",), "ev_defense_not_acting"),
        EventSpec("C5_remote_dispatch_loss", "physical", "C5", ("area", "node"), "ev_remote_dispatch_loss"),
        EventSpec("D1_telemetry_loss", "digital", None, ("area", "node"), "ev_telemetry_loss"),
        EventSpec("D2_telemetry_delay", "digital", None, ("area", "node"), "ev_telemetry_delay"),
        EventSpec("D3_unreliable_data", "digital", None, ("area", "node"), "ev_unreliable_data"),
        EventSpec("D4_comms_loss", "digital", None, ("area", "node"), "ev_comms_loss"),
        EventSpec("D5_false_alarms", "digital", None, ("area", "node"), "ev_false_alarms"),
        EventSpec(
            "D6_external_dependency_loss", "digital", None, ("area", "node"), "ev_external_dependency_loss"
        ),
        EventSpec("E1_demand_surge", "external", None, ("area", "node", "zone"), "ev_demand_surge"),
        EventSpec("E2_renewable_drop", "external", None, ("zone",), "ev_renewable_drop"),
    )
}


@dataclass(frozen=True)
class ActionSpec:
    id: str
    label_key: str
    proposers: frozenset[Role]
    needs_approval: bool
    weight: str  # light | medium | heavy | restore
    target: str  # area | corridor | defense
    reversible: bool
    remote_dependent: bool  # needs remote control or manual operation in the target area
    info_only: bool  # gathers information; never counted as a wrong decision


ACTIONS: dict[str, ActionSpec] = {
    a.id: a
    for a in (
        ActionSpec(
            "isr_tasking", "act_isr_tasking", frozenset({Role.ISR}), False, "light", "area", True, False, True
        ),
        ActionSpec(
            "field_verification",
            "act_field_verification",
            frozenset({Role.OPS, Role.ISR}),
            False,
            "light",
            "area",
            True,
            False,
            True,
        ),
        ActionSpec(
            "manual_operation",
            "act_manual_operation",
            frozenset({Role.OPS}),
            True,
            "medium",
            "area",
            True,
            False,
            False,
        ),
        ActionSpec(
            "backup_comms",
            "act_backup_comms",
            frozenset({Role.OPS}),
            False,
            "medium",
            "area",
            True,
            False,
            False,
        ),
        ActionSpec(
            "digital_segmentation",
            "act_digital_segmentation",
            frozenset({Role.OPS}),
            True,
            "heavy",
            "area",
            True,
            False,
            False,
        ),
        ActionSpec(
            "preventive_load_reduction",
            "act_preventive_load_reduction",
            frozenset({Role.STAB}),
            True,
            "heavy",
            "area",
            True,
            True,
            False,
        ),
        ActionSpec(
            "fast_reserve",
            "act_fast_reserve",
            frozenset({Role.STAB}),
            False,
            "medium",
            "area",
            True,
            True,
            False,
        ),
        ActionSpec(
            "battery_support",
            "act_battery_support",
            frozenset({Role.STAB, Role.LOG}),
            False,
            "medium",
            "area",
            True,
            True,
            False,
        ),
        ActionSpec(
            "rearm_defense",
            "act_rearm_defense",
            frozenset({Role.STAB}),
            False,
            "medium",
            "defense",
            True,
            True,
            False,
        ),
        ActionSpec(
            "islanding_prep",
            "act_islanding_prep",
            frozenset({Role.STAB}),
            True,
            "heavy",
            "corridor",
            False,
            False,
            False,
        ),
        ActionSpec(
            "restore_element",
            "act_restore_element",
            frozenset({Role.OPS}),
            False,
            "restore",
            "area",
            False,
            True,
            False,
        ),
        ActionSpec(
            "request_external_support",
            "act_request_external_support",
            frozenset({Role.LOG}),
            False,
            "light",
            "area",
            False,
            False,
            False,
        ),
    )
}

# pairs of actions on the same target that pull in opposite directions (C2 resolves them)
CONFLICTS = {
    frozenset({"backup_comms", "digital_segmentation"}),
    frozenset({"restore_element", "preventive_load_reduction"}),
    frozenset({"restore_element", "islanding_prep"}),
}

OBJECTIVES = (
    "reduce_observability",
    "raise_uncertainty",
    "pressure_resources",
    "provoke_unnecessary_actions",
    "complicate_recovery",
)
