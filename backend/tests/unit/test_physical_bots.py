"""Physical contract of the bots (docs/agents.md): the theatre grid carries frequency, RoCoF and the island
verdict per area; supervision filters them like any other value; Stabilisation acts on them; the adversary
never sees them."""

import dataclasses

from cascadasen.domain.agents.base import AdversaryView, AgentView
from cascadasen.domain.agents.stabilization import StabilizationAgent
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import RunConfig, Simulation
from cascadasen.domain.theater.decisions import COA, Intent
from cascadasen.domain.theater.grid import TheaterGrid
from cascadasen.domain.theater.state import Alarm, AreaObs, ObservedState


def _grid(toy_world) -> TheaterGrid:
    net, point = toy_world.load("nov2026-1300")
    return TheaterGrid.from_point(net, point)


def test_grid_reads_frequency_rocof_and_verdict_per_area(toy_world):
    g = _grid(toy_world)
    assert g.freq_hz["T1"] == 50.0 and g.island_result["T2"] == "maintains"
    g.disabled.add("edac:centro_sur")  # no load shedding: frequency settles where reserve and damping meet
    g.trip("T1", 40.0, "sync")
    g.run_cascade([])
    assert all(g.freq_hz[a] < 49.0 for a in ("T1", "T2", "T3"))
    assert g.rocof_hz_s["T1"] < 0 and g.island_result["T1"] == "maintains"
    assert g.last_islands[0]["areas"] == ["T1", "T2", "T3"] and g.last_islands[0]["inertia_mws"] > 0
    g.settle_frequency()  # secondary control between cycles
    assert g.freq_hz["T1"] == 50.0 and g.rocof_hz_s["T1"] == 0.0


def test_batteries_hold_frequency_better_than_nothing(toy_world):
    plain, helped = _grid(toy_world), _grid(toy_world)
    for g in (plain, helped):
        g.disabled.add("edac:centro_sur")
        g.trip("T1", 40.0, "sync")
    helped.battery["T2"] = 30.0
    plain.run_cascade([])
    helped.run_cascade([])
    assert helped.nadir_hz["T2"] > plain.nadir_hz["T2"]


def test_supervision_shows_frequency_and_flags_the_band(toy_world):
    sim = Simulation(toy_world, RunConfig(template="open_field", seed=3, horizon=6, stochastic=False))
    sim.inject("C1_generation_loss", "T1", params={"mw": 40})
    sim.step(1)
    lt = sim.real.last_transient
    assert lt["islands"] and lt["islands"][0]["rocof_hz_s"] < 0 and lt["islands"][0]["min_hz"] <= 49.0
    obs = sim.observations[-1]
    kinds = {a.kind for a in obs.alarms}
    # over-shedding on the small toy island leaves it above 51 Hz: out of the operating band
    assert "frequency_out_of_band" in kinds and "frequency_event" in kinds
    assert all(a.freq_hz is not None for a in obs.areas)
    assert obs.as_dict()["areas"]["T1"]["freq_hz"] is not None


def test_blind_or_unreliable_supervision_hides_the_frequency(toy_world):
    sim = Simulation(toy_world, RunConfig(template="open_field", seed=3, horizon=6, stochastic=False))
    sim.inject("D1_telemetry_loss", "T2")
    sim.inject("D3_unreliable_data", "SE_S1")
    sim.inject("C1_generation_loss", "T1", params={"mw": 40})
    sim.step(1)
    obs = sim.observations[-1]
    assert obs.area("T2").freq_hz is None  # telemetry lost: nothing to read
    assert obs.area("T3").freq_hz == 50.0  # unreliable data looks normal


def _view(areas, alarms=(), corridors=(("T1-T2", "closed"), ("T2-T3", "closed")), resources=None, cycle=3):
    cfg = theater_config()
    mission = next(iter(cfg.missions.values()))
    obs = ObservedState(
        cycle,
        tuple(
            AreaObs(a, 100.0, 100.0, True, 0, "primary", 1.0, False, False, f, r)
            for a, (f, r) in areas.items()
        ),
        corridors,
        tuple(Alarm(a, k) for a, k in alarms),
    )
    res = resources if resources is not None else {"battery_mw": 300.0, "fast_reserve_mw": 400.0}
    intent = Intent(1, ("T2",), 0.5, 0.0, False, "intent_alert")
    return AgentView(
        "stabilization",
        cycle,
        obs,
        (),
        mission,
        cfg.policies["C"],
        intent=intent,
        resources=tuple(res.items()),
    )


def _stab(toy_world) -> StabilizationAgent:
    net = toy_world.network
    return StabilizationAgent(net, {a: 100.0 for a in net.order}, {})


def test_stabilisation_sends_batteries_on_steep_rocof(toy_world):
    stab = _stab(toy_world)
    view = _view({"T1": (49.6, -1.4), "T2": (49.6, -1.4), "T3": (49.6, -1.4)}, alarms=[("T2", "high_rocof")])
    coas = stab.propose(view)
    assert any(c.action == "battery_support" and c.target == "T2" for c in coas)


def test_stabilisation_sheds_when_under_frequency_and_nothing_left(toy_world):
    stab = _stab(toy_world)
    view = _view(
        {"T1": (48.7, -0.2), "T2": (48.7, -0.2), "T3": (48.7, -0.2)},
        alarms=[("T1", "frequency_out_of_band")],
        resources={"battery_mw": 0.0, "fast_reserve_mw": 0.0},
    )
    coas = stab.propose(view)
    assert [c.target for c in coas if c.action == "preventive_load_reduction"] == ["T1"]  # T2 is protected


def test_stabilisation_vetoes_unsafe_recovery(toy_world):
    stab = _stab(toy_world)
    out = _view(
        {"T1": (48.8, 0.0), "T2": (50.0, 0.0), "T3": (50.0, 0.0)}, alarms=[("T1", "frequency_out_of_band")]
    )
    stab.propose(out)
    restore = [COA("restore_element", "T1", "operations", "ops_restore_supply")]
    assert stab.review(out, restore) == {"restore_element:T1": "stab_wait_for_stability"}

    stab = _stab(toy_world)
    volt = _view({a: (50.0, 0.0) for a in ("T1", "T2", "T3")}, alarms=[("T3", "voltage_limited")])
    stab.propose(volt)
    restore = [COA("restore_element", "T2-T3", "operations", "ops_restore_corridor")]
    assert stab.review(volt, restore) == {"restore_element:T2-T3": "stab_voltage_uncertain"}

    stab = _stab(toy_world)
    weak = _view({a: (50.0, 0.0) for a in ("T1", "T2", "T3")}, alarms=[("T3", "low_inertia")])
    stab.propose(weak)
    split = [COA("islanding_prep", "T2-T3", "operations", "ops_preventive_isolation")]
    assert stab.review(weak, split) == {"islanding_prep:T2-T3": "stab_low_inertia"}


def test_adversary_view_has_no_physical_quantities():
    names = {f.name for f in dataclasses.fields(AdversaryView)}
    assert not {n for n in names if any(k in n for k in ("freq", "rocof", "inertia", "hz", "voltage"))}
