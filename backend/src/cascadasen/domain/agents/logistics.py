"""Logistics agent: manages reserves, redundancy and external support; reports freedom of action."""

from __future__ import annotations

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.simulation.network import ReducedNetwork
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.decisions import COA

LOG = Role.LOG.value


class LogisticsAgent:
    role = Role.LOG

    def __init__(self, network: ReducedNetwork) -> None:
        self.net = network
        self.requested: dict[str, int] = {}

    def propose(self, view: AgentView) -> list[COA]:
        coas = []
        for alarm in view.observed.alarms:
            a = alarm.area
            if alarm.kind == "external_service" and view.cycle - self.requested.get(a, -99) >= 4:
                coas.append(
                    COA("request_external_support", a, LOG, "log_request_external_support", benefit=0.8)
                )
                self.requested[a] = view.cycle
        return coas

    def review(self, view: AgentView, coas: list[COA]) -> dict[str, str]:
        """Flags durable resource use that would leave the commander's reserve exposed."""
        vetoes = {}
        keep = view.intent.reserve_keep if view.intent else 0.0
        if keep <= 0:
            return vetoes
        crews_left = view.available("field_crews")
        for c in coas:
            if c.action == "manual_operation" and crews_left <= 1:
                vetoes[c.key] = "log_keep_crew_for_recovery"
        return vetoes

    def freedom(self, view: AgentView) -> int:
        """How many resource pools still allow at least one more action."""
        return sum(1 for _, v in view.resources if v >= 1)
