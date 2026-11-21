"""Stabilisation agent: protects physical constraints and prioritises continuity and safe recovery.

It reasons on its own estimate of the grid (the day-ahead plan corrected by what supervision
shows), never on the real grid. It proposes reserve, batteries, re-arming defences and, under the
preventive policy, load reduction; it vetoes restorations into an island that is still unstable.
"""

from __future__ import annotations

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.decisions import COA

STAB = Role.STAB.value


class StabilizationAgent:
    role = Role.STAB

    def __init__(
        self, network: TheaterNetwork, plan_load: dict[str, float], defense_areas: dict[str, list[str]]
    ):
        self.net = network
        self.plan = dict(plan_load)
        self.defense_areas = defense_areas
        self.unstable_until = -1

    def _defense_for(self, area: str) -> str | None:
        for did, areas in self.defense_areas.items():
            if did.startswith("edac:") or did == "pdce_zn":
                if area in areas:
                    return did
        return None

    def propose(self, view: AgentView) -> list[COA]:
        obs, isr, intent, policy = view.observed, view.isr, view.intent, view.policy
        active = set(view.active)
        coas: list[COA] = []

        def add(action: str, target: str, key: str, benefit: float, risk: float = 0.0) -> None:
            if f"{action}:{target}" not in active:
                coas.append(COA(action, target, STAB, key, benefit=benefit, risk=risk))

        frequency = any(a.kind == "frequency_event" for a in obs.alarms)
        if frequency:
            self.unstable_until = view.cycle + 1
        escalation = intent.escalation if intent else 0
        protect = [a for a in (intent.protect if intent else ()) if a in self.net.areas]
        preemptive = (policy.preventive and escalation >= 1) or (policy.id == "C" and escalation >= 2)
        if frequency or preemptive:
            for a in protect:
                o = obs.area(a)
                if o.energized is not False:
                    if view.available("battery_mw") >= 100:
                        add("battery_support", a, "stab_fast_support_priority_area", 0.6)
                    if view.available("fast_reserve_mw") >= 100:
                        add("fast_reserve", a, "stab_reserve_priority_area", 0.5)
                    break
        for alarm in obs.alarms:
            if alarm.kind == "defense_fault":
                did = self._defense_for(alarm.area)
                if did:
                    add("rearm_defense", did, "stab_rearm_defense", 0.9)
        if policy.preventive and escalation >= 2 and isr:
            candidates = [a for a in isr.affected if a not in protect and a not in isr.outages]
            if candidates:
                add("preventive_load_reduction", candidates[0], "stab_preventive_margin", 0.4, 0.2)
        return coas

    def review(self, view: AgentView, coas: list[COA]) -> dict[str, str]:
        """Vetoes on its own estimate: no restoration while the island is still swinging."""
        vetoes: dict[str, str] = {}
        if view.cycle <= self.unstable_until:
            for c in coas:
                if c.action == "restore_element" and c.target in self.net.areas:
                    vetoes[c.key] = "stab_wait_for_stability"
        return vetoes
