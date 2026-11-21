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
from cascadasen.domain.theater.areas import bus_id
from cascadasen.domain.theater.world import TheaterWorld

REFERENCE_OPERATING_POINT = "midday_2026"


class SimulationService:
    def __init__(
        self,
        network: ReducedNetwork,
        physics: Physics | None = None,
        interpreter: Interpreter | None = None,
        advisor: CommanderAdvisor | None = None,
        world: TheaterWorld | None = None,
    ) -> None:
        self.network = network  # 13-area network of POST /simulate (domain/simulation)
        self.physics = physics or Physics.load()
        self.simulator = PhysicsSimulator(network, self.physics)
        self.world = world  # mapa 3 network and operating points: the strategic theatre runs here
        self.runs = RunManager(world, self.physics, interpreter=interpreter, advisor=advisor)
        self.campaigns = CampaignRunner(world, self.physics)

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
        return catalog(self.world)

    def theater_network(self, point: str | None = None) -> dict[str, Any]:
        """The mapa 3 network of a point (same `Network` shape as web/public/cache/network-<year>.json)
        plus the operating areas, corridors and defence functions the theatre uses."""
        points = self.world.points()
        point = point or ("nov2026-1300" if "nov2026-1300" in points else points[0])
        if point not in points:
            raise KeyError(point)
        net, op = self.world.load(point)
        b = net.buses
        ids = [bus_id(i) for i in range(b.size)]
        return {
            "point": point,
            "points": points,
            "nodes": [
                {
                    "id": ids[i],
                    "name": b.names[i],
                    "lon": b.lon[i],
                    "lat": b.lat[i],
                    "kv": b.kv[i],
                    "zone": b.zone(i),
                    "map_nodes": b.map_nodes[i],
                    "area": net.area_of_bus[i],
                }
                for i in range(b.size)
            ],
            "lines": [
                {
                    "id": ln.id,
                    "a": ids[ln.a],
                    "b": ids[ln.b],
                    "kv": ln.kv,
                    "capacity_mw": round(ln.capacity_mw, 1),
                    "x_pu": ln.x_pu,
                    "map_edges": list(ln.map_edges),
                    "branches": list(ln.branches),
                    "corridor": net.line_corridor.get(ln.id),
                }
                for ln in b.lines
            ],
            "buses": {
                ids[i]: {
                    "gen_mw": round(float(op.gen[i]), 1),
                    "load_mw": round(float(op.load[i]), 1),
                    "people": round(float(op.people[i])),
                }
                for i in range(b.size)
            },
            "areas": [
                {
                    "id": a.id,
                    "name": a.name,
                    "zone": a.zone,
                    "lat": a.lat,
                    "lon": a.lon,
                    "population": round(a.population),
                    "buses": a.bus_ids,
                    "anchor_bus": bus_id(a.anchor_bus) if a.anchor_bus is not None else None,
                }
                for a in (net.areas[k] for k in net.order)
            ],
            "corridors": [
                {"id": c.id, "a": c.a, "b": c.b, "lines": list(c.lines)} for c in net.corridors.values()
            ],
            "defenses": {k: v for k, v in net.defense_areas().items()},
            "zones": net.zones,
        }
