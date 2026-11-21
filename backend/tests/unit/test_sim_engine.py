"""DC power flow, island frequency model and cascade on a hand-built three-area network."""

import pytest

from cascadasen.domain.simulation.defenses import DefenseSet
from cascadasen.domain.simulation.engine import Change, run_transient
from cascadasen.domain.simulation.frequency import IslandInput, simulate_island
from cascadasen.domain.simulation.grid import GridState, Physics
from cascadasen.domain.simulation.network import Area, Corridor, CorridorPart, ReducedNetwork
from cascadasen.domain.simulation.powerflow import dc_flow, islands

PH = Physics.load()
DEF = DefenseSet.load("design_2026")


def _area(i, aid, zone):
    return Area(aid, aid, zone, i, -70.0, -30.0 - i, 1_000_000, {"termica": 2000.0}, 0.0, (), (), None)


def _corr(a, b, cls, x, cap):
    return Corridor(
        f"{a}-{b}/{cls}", a, b, cls, (CorridorPart(f"{a}{b}{cls}", x, cap, (f"L{a}{b}{cls}",), False),), "t"
    )


@pytest.fixture
def net():
    areas = {a.id: a for a in (_area(0, "X", "NC"), _area(1, "Y", "CE"), _area(2, "Z", "CS"))}
    cs = [
        _corr("X", "Y", "500", 0.01, 2000.0),
        _corr("X", "Y", "220", 0.03, 400.0),
        _corr("Y", "Z", "220", 0.02, 1500.0),
    ]
    return ReducedNetwork(areas, {c.id: c for c in cs}, {}, {}, {}, 100.0, [])


def _state(gen, load):
    return GridState(
        operating_point="test",
        load_mw=dict(load),
        served_mw=dict(load),
        gen_mw={a: {"termica": g} for a, g in gen.items()},
        tripped_mw={a: {} for a in gen},
        kinetic_mws={a: 4.0 * g for a, g in gen.items()},
        h_phys={"termica": 4.0},
        reserve_share={a: 0.04 for a in gen},
        sync_techs=frozenset({"termica"}),
    )


def test_dc_flow_splits_by_reactance(net):
    st = _state({"X": 1600, "Y": 500, "Z": 400}, {"X": 400, "Y": 1000, "Z": 1100})
    f = dc_flow(net, st)
    assert f["X-Y/500"] + f["X-Y/220"] == pytest.approx(1200, abs=1e-6)
    assert f["X-Y/500"] / f["X-Y/220"] == pytest.approx(3.0, rel=1e-6)  # 1/0.01 vs 1/0.03
    assert f["Y-Z/220"] == pytest.approx(700, abs=1e-6)


def test_initial_rocof_matches_swing_equation():
    island = IslandInput("I1", ["X"], 9000, 9000, 0, 10000, 40_000_000.0 / 1000, 0, 0)
    island.kinetic_mws = 40_000.0  # 40 GVAs
    tr = simulate_island(island, DEF, PH, full=False)
    assert tr.rocof_initial == pytest.approx(-PH.f0 * 1000 / (2 * 40_000), abs=0.01)


def test_edac_steps_fire_below_threshold_and_battery_helps():
    base = dict(
        id="I1",
        areas=["X"],
        gen_mw=8000,
        sync_mw=8000,
        nonsync_mw=0,
        load_mw=10000,
        kinetic_mws=40_000.0,
        reserve_mw=200,
        battery_mw=0,
    )
    tr = simulate_island(IslandInput(**base), DEF, PH)
    assert tr.result == "maintains" and tr.shed_mw > 0
    assert tr.shed_events and all(e.label_key == "edac_step" for e in tr.shed_events)
    with_bat = simulate_island(IslandInput(**{**base, "battery_mw": 1500}), DEF, PH)
    assert with_bat.f_min > tr.f_min and with_bat.shed_mw < tr.shed_mw


def test_weak_link_separation_forms_islands(net):
    st = _state({"X": 1000, "Y": 900, "Z": 600}, {"X": 400, "Y": 1000, "Z": 1100})
    res = run_transient(net, st, [Change("open_corridor", "X-Y/500")], DEF, PH, full=False)
    assert res.weak_links and res.weak_links[0][0] == "X-Y/220"  # 600 MW on a 400 MW link
    assert [r.areas for r in res.islands] == [["Y", "Z"], ["X"]]
    assert any(e["type"] == "island_formed" for e in res.events)
    south = res.islands[0]
    assert south.result == "maintains" and south.trace.shed_mw > 0  # EDAC holds the importing island
    assert ["Y", "Z"] in islands(net, res.state)


def test_unknown_island_collapse_loses_load(net):
    st = _state({"X": 3000, "Y": 0.0001, "Z": 0.0001}, {"X": 100, "Y": 1450, "Z": 1450})
    res = run_transient(
        net, st, [Change("open_corridor", "X-Y/500"), Change("open_corridor", "X-Y/220")], DEF, PH, full=False
    )
    south = next(r for r in res.islands if "Y" in r.areas)
    assert south.result == "blackout"
    assert res.state.served_mw["Y"] == 0 and res.people_without_power >= 2_000_000
