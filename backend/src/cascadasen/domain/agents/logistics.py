"""Logistics agent: manages reserves, redundancy, field crews and external support; reports freedom
of action. It knows where its crews are and does not send one that would arrive too late."""

from __future__ import annotations

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.decisions import COA

LOG = Role.LOG.value


class LogisticsAgent:
    role = Role.LOG

    def __init__(
        self,
        network: TheaterNetwork,
        crew_actions: frozenset[str] = frozenset(),
        max_eta: int | None = None,
        sites: dict[str, list[str]] | None = None,
    ) -> None:
        self.net = network
        self.requested: dict[str, int] = {}
        self.crew_actions, self.max_eta = crew_actions, max_eta
        self.sites = sites or {}  # defence id -> areas where a crew can act on it

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
        vetoes = self._too_far(view, coas)
        keep = view.intent.reserve_keep if view.intent else 0.0
        if keep <= 0:
            return vetoes
        crews_left = view.available("field_crews")
        for c in coas:
            if c.action == "manual_operation" and crews_left <= 1:
                vetoes.setdefault(c.key, "log_keep_crew_for_recovery")
        return vetoes

    def _too_far(self, view: AgentView, coas: list[COA]) -> dict[str, str]:
        """Crew actions whose nearest free crew would arrive after `max_eta` cycles."""
        if self.max_eta is None or not view.crew_eta:
            return {}
        eta = dict(view.crew_eta)
        out = {}
        for c in coas:
            if c.action not in self.crew_actions:
                continue
            sites = self._sites(c.target)
            best = min((eta[s] for s in sites if s in eta), default=None)
            if best is None or best > self.max_eta:
                out[c.key] = "log_crew_too_far"
        return out

    def _sites(self, target: str) -> list[str]:
        if target in self.net.areas:
            return [target]
        if target in self.net.corridors:
            c = self.net.corridors[target]
            return [c.a, c.b]
        return self.sites.get(target, [])
