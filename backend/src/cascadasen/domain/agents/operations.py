"""Operations agent: proposes operational measures from the ISR picture and what supervision shows."""

from __future__ import annotations

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.decisions import COA

OPS = Role.OPS.value
RESEGMENT_AFTER = 6  # cycles (30 min): a clean-up that did not hold is tried again


class OperationsAgent:
    role = Role.OPS

    def __init__(self, network: TheaterNetwork) -> None:
        self.net = network
        self.verified: dict[str, int] = {}
        self.no_ack: set[str] = set()
        self.contained: dict[str, int] = {}  # area -> cycle it was last segmented to contain an intrusion

    def propose(self, view: AgentView) -> list[COA]:
        isr, policy, obs = view.isr, view.policy, view.observed
        active = set(view.active)
        coas: list[COA] = []
        for fb in view.feedback:
            if fb.observable_code == "remote_command_not_acknowledged":
                self.no_ack.add(fb.target)
        alarms = {(a.area, a.kind) for a in obs.alarms}

        def add(action: str, target: str, key: str, benefit: float, risk: float = 0.0) -> None:
            if f"{action}:{target}" not in active:
                coas.append(COA(action, target, OPS, key, benefit=benefit, risk=risk))

        if isr:
            for a in isr.verify[:3]:
                if view.cycle - self.verified.get(a, -99) >= 3:
                    add("field_verification", a, "ops_verify_area", 0.6)
                    self.verified[a] = view.cycle
        for o in obs.areas:
            a = o.area
            suspicion = isr.suspicion_of(a) if isr else 0.0
            if o.comms == "down" or (a, "comms_lost") in alarms:
                add("backup_comms", a, "ops_restore_supervision_path", 0.8)
            if (a, "control_lost") in alarms or a in self.no_ack:
                add("manual_operation", a, "ops_take_local_control", 0.8, 0.1)
            if (a, "data_anomaly") in alarms and suspicion >= 0.5:
                add("digital_segmentation", a, "ops_isolate_untrusted_data", 0.7, 0.3)
            comms_lost = (
                o.comms in ("backup", "down") or (a, "comms_lost") in alarms
            )  # backup comms: still not trusted
            if f"digital_segmentation:{a}" in active:
                self.contained[a] = view.cycle  # segmentation in force: next time, repair instead
            if view.containment and comms_lost:
                # isolate first, then repair; isolate again if supervision is still lost RESEGMENT_AFTER cycles later
                if view.cycle - self.contained.get(a, -99) >= RESEGMENT_AFTER:
                    add("digital_segmentation", a, "ops_contain_intrusion", 0.9, 0.3)
                elif (
                    f"digital_segmentation:{a}" not in active
                ):  # segmentation gave remote control back: repair
                    add("restore_element", a, "ops_repair_after_containment", 0.9)
            if policy.preventive and suspicion >= 0.3:
                add("digital_segmentation", a, "ops_preventive_isolation", 0.5, 0.3)
                add("manual_operation", a, "ops_preventive_local_control", 0.5, 0.1)
        for a in view.outages():
            add("restore_element", a, "ops_restore_supply", 1.0)
        for cid, status in obs.corridors:
            if status == "open":
                add("restore_element", cid, "ops_restore_corridor", 0.7)
        return coas
