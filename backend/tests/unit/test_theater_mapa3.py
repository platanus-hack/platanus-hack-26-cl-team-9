"""The strategic theatre on the mapa 3 network: areas group buses, resolve speaks the viewer's ids,
physics is the mapa 3 cascade engine, and every id a snapshot emits exists in the network."""

import numpy as np

from cascadasen.domain.cascade.engine import run_cascade_workflow
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.domain.theater.grid import Change, TheaterGrid


def test_areas_group_buses_by_latitude_and_corridors_cross_boundaries(toy_world):
    net = toy_world.network
    assert {a: net.areas[a].bus_ids for a in net.order} == {
        "T1": ["B000", "B001"],
        "T2": ["B002", "B003"],
        "T3": ["B004", "B005"],
    }
    assert net.corridors["T1-T2"].lines == ("R1", "R2") and net.corridors["T2-T3"].lines == ("R4", "R5")
    assert net.areas["T2"].anchor_bus == 2  # largest load


def test_resolve_speaks_the_viewer_ids(toy_world):
    net = toy_world.network
    assert net.resolve("B003").area == "T2"
    assert net.resolve("SE_S1").id == "B004" and net.resolve("SE_S1").area == "T3"
    assert net.resolve("R4").corridor == "T2-T3"
    assert net.resolve("R3").kind == "line" and net.resolve("R3").area == "T2"


def test_a_corridor_opening_is_exactly_the_mapa3_cascade(toy_world):
    net, point = toy_world.load("nov2026-1300")
    grid = TheaterGrid.from_point(net, point)
    lines = grid.apply(Change("open_corridor", "T2-T3"))[0]
    theatre = grid.run_cascade(lines)
    viewer = run_cascade_workflow(net.buses, point, list(net.corridors["T2-T3"].lines))
    assert theatre["summary"] == viewer["summary"] and theatre["frames"] == viewer["frames"]


def test_trip_spreads_over_the_area_and_takes_inertia_with_it(toy_world):
    net, point = toy_world.load("nov2026-1300")
    grid = TheaterGrid.from_point(net, point)
    before = grid.inertia.copy()
    assert grid.trip("T1", 150.0, "sync") == 150.0
    assert grid.sync_gen("T1") == 150.0 and grid.inertia[0] == before[0] / 2
    assert grid.tripped("T1", "sync") == 150.0


def test_snapshots_only_emit_ids_the_network_has(toy_world):
    sim = Simulation(
        toy_world,
        RunConfig(
            template="open_field",
            seed=4,
            horizon=12,
            adversary=AdversaryConfig(True, "complicate_recovery", 12, True),
        ),
    )
    sim.inject("C3_transmission_opening", "T2-T3", cause="intentional")
    sim.run_to_end()
    buses = {f"B{i:03d}" for i in range(sim.network.buses.size)}
    lines = {ln.id for ln in sim.network.buses.lines}
    transients = 0
    for s in sim.snapshots:
        assert set(s["grid"]["dark"]) <= buses and set(s["grid"]["edges"]) <= lines
        assert set(s["areas"]) == set(sim.network.order)
        for c in s["crews"]:
            assert c["bus"] in buses
        if s["transient"]:
            transients += 1
            for f in s["transient"]["frames"]:
                assert set(f["dark"]) <= buses and set(f["edges"]) <= lines
    assert transients >= 1
    # the adversary never names a bus or a line
    for e in sim.real.effects:
        if e.source == "adversary":
            assert e.target not in buses and e.target not in lines


def test_restoration_reenergizes_a_dark_area(toy_world):
    net, point = toy_world.load("nov2026-1300")
    grid = TheaterGrid.from_point(net, point)
    grid.dark |= {4, 5}
    grid.load[[4, 5]] = 0.0
    grid.sync[4] = 0.0
    assert "T3" in grid.blackout_areas
    for _ in range(6):
        grid.restore_step("T3", 0.3, 0.34)
    assert "T3" not in grid.blackout_areas and np.isclose(grid.served_mw["T3"], grid.load_mw["T3"], atol=1.0)
