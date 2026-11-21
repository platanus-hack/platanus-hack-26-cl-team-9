"""Facade the HTTP API uses for everything simulation: reduced network, physical contingencies,
strategic runs and campaigns. Built once per snapshot."""

from __future__ import annotations

from typing import Any

from cascadasen.application.run_campaign import CampaignRunner
from cascadasen.application.run_experiment import RunManager, catalog
from cascadasen.application.simulate import PhysicsSimulator, SimulateCommand
from cascadasen.domain.model import GridSnapshot
from cascadasen.domain.ports import CommanderAdvisor, Interpreter
from cascadasen.domain.simulation.grid import Physics, build_state
from cascadasen.domain.simulation.network import NetworkSpec, ReducedNetwork, build_reduced_network

REFERENCE_OPERATING_POINT = "midday_2026"


class SimulationService:
    def __init__(
        self,
        network: ReducedNetwork,
        physics: Physics | None = None,
        interpreter: Interpreter | None = None,
        advisor: CommanderAdvisor | None = None,
    ) -> None:
        self.network = network
        self.physics = physics or Physics.load()
        self.simulator = PhysicsSimulator(network, self.physics)
        self.runs = RunManager(network, self.physics, interpreter=interpreter, advisor=advisor)
        self.campaigns = CampaignRunner(network, self.physics)

    @classmethod
    def from_snapshot(
        cls, snapshot: GridSnapshot, spec: NetworkSpec | None = None, **adapters: Any
    ) -> SimulationService:
        return cls(build_reduced_network(snapshot, spec), **adapters)

    # ------------------------------------------------------------- network

    def network_view(self) -> dict[str, Any]:
        net = self.network
        state = build_state(net, REFERENCE_OPERATING_POINT, self.physics)
        areas = [
            {
                "id": a.id,
                "name": a.name,
                "zone": a.zone,
                "lon": a.lon,
                "lat": a.lat,
                "population": a.population,
                "demand_mw": round(state.load_mw[a.id], 1),
                "generation_mw": round(state.gen(a.id), 1),
                "installed_mw": a.installed_mw,
                "storage_mw": a.storage_mw,
                "main_node": a.main_node,
                "anchors": list(a.anchors),
                "aggregates": list(a.aggregates),
            }
            for a in (net.areas[k] for k in net.order)
        ]
        corridors = [
            {
                "id": c.id,
                "a": c.a,
                "b": c.b,
                "kv_class": c.kv_class,
                "x_pu": c.x_pu,
                "capacity_mw": c.capacity_mw,
                "lines": c.lines,
                "members": list(c.members),
                "is_assumption": c.is_assumption,
                "source": c.source,
            }
            for c in net.corridors.values()
        ]
        return {
            "version": 1,
            "reference_operating_point": REFERENCE_OPERATING_POINT,
            "zones": net.zones,
            "areas": areas,
            "corridors": corridors,
            "provenance": [p.as_dict() for p in net.provenance],
        }

    def simulate(self, cmd: SimulateCommand) -> dict[str, Any]:
        return self.simulator.simulate(cmd)

    def catalog(self) -> dict[str, Any]:
        return catalog(self.network)
