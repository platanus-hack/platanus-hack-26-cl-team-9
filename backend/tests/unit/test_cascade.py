"""Cascade engine: reduction, DC flow, frequency model, EDAC totals and the overload cascade on a toy grid."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cascadasen.domain.cascade.engine import CascadeParams, run_cascade_workflow
from cascadasen.domain.cascade.flow import dc_flow, find_islands
from cascadasen.domain.cascade.frequency import (
    CENTRO_SUR_ZONES,
    F0,
    IslandInput,
    Params,
    edac_tables,
    simulate_island,
)
from cascadasen.domain.cascade.network import Line, ReducedNetwork, reduce_network, substation_of
from cascadasen.domain.cascade.scenario import OperatingPoint, load_network_and_point

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"


def _bus(name, kv, node=None):
    return {"name": name, "kv": kv, "lat": -33.0, "lon": -70.0, "node": node}


def _branch(name, a, b, mva, x, kind="Line", year=2020):
    return {
        "name": name,
        "bus0": a,
        "bus1": b,
        "s_nom_mva": mva,
        "x_pu": x,
        "kv": 220,
        "asset_type": kind,
        "build_year": year,
        "edges": [f"L_{name}"],
    }


def _toy_net(caps=(200.0, 200.0, 100.0)) -> ReducedNetwork:
    """A(0) - B(1), A - C(2), B - C. Equal reactances."""
    lines = [
        Line("R0", 0, 1, caps[0], 0.01, 220, ("ab",), ()),
        Line("R1", 0, 2, caps[1], 0.01, 220, ("ac",), ()),
        Line("R2", 1, 2, caps[2], 0.01, 220, ("bc",), ()),
    ]
    return ReducedNetwork(
        names=["A", "B", "C"],
        lat=[-33.0] * 3,
        lon=[-70.0] * 3,
        kv=[220.0] * 3,
        model_buses=[["A_220"], ["B_220"], ["C_220"]],
        map_nodes=[[], [], []],
        lines=lines,
        index={"A": 0, "B": 1, "C": 2},
        bus_of_model_bus={"A_220": 0, "B_220": 1, "C_220": 2},
    )


def _toy_point(gen=(300.0, 0.0, 0.0), load=(0.0, 150.0, 150.0)) -> OperatingPoint:
    return OperatingPoint(
        "toy",
        "toy",
        np.array(load),
        np.array(gen),
        np.array([gen[0], 0, 0]),
        np.array([30000.0, 0, 0]),
        np.array([0.0, 1000.0, 1000.0]),
    )


def test_substation_name_drops_voltage_suffix():
    assert substation_of("S/E ALTO JAHUEL_500") == "S/E ALTO JAHUEL"
    assert substation_of("TAP TUNICHE_154_II") == "TAP TUNICHE"
    assert substation_of("S/E SAUZAL_110_BP1") == "S/E SAUZAL"


def test_reduction_folds_transformers_and_parallel_lines_and_skips_later_links():
    snapshot = {
        "model_buses": [_bus("X_500", 500, "N1"), _bus("X_220", 220, "N1"), _bus("Y_220", 220, "N2")],
        "model_branches": [
            _branch("trafo", "X_500", "X_220", 1800, 0.006, "Transformer"),
            _branch("l1", "X_220", "Y_220", 100, 0.02),
            _branch("l2", "X_220", "Y_220", 100, 0.02),
            _branch("future", "X_500", "Y_220", 3000, 0.005, year=2029),
        ],
    }
    net = reduce_network(snapshot, year=2026)
    assert net.size == 2 and len(net.lines) == 1
    line = net.lines[0]
    assert line.capacity_mw == 200 and line.x_pu == pytest.approx(0.01) and set(line.branches) == {"l1", "l2"}
    assert (
        reduce_network(snapshot).lines[0].capacity_mw == 3200
    )  # without a year the 2029 link joins the same pair


def test_dc_flow_splits_by_reactance_and_conserves_power():
    net = _toy_net()
    injection = np.array([100.0, 0.0, -100.0])
    flows = dc_flow(net, set(), injection, find_islands(net, set()))
    # direct A-C path has half the reactance of A-B-C: 2/3 of the power goes direct
    assert flows[1] == pytest.approx(66.67, abs=0.1) and flows[0] == pytest.approx(33.33, abs=0.1)
    assert flows[0] == pytest.approx(flows[2], abs=1e-6)


def test_islands_follow_open_lines():
    net = _toy_net()
    assert len(find_islands(net, set())) == 1
    assert sorted(len(i) for i in find_islands(net, {"R0", "R2"})) == [1, 2]


def test_initial_frequency_slope_matches_the_cen_reference():
    # docs/stack.md 4.4: a 3,000 MW loss with 44.3 GVAs gives about 1.69 Hz/s
    island = IslandInput(
        inertia_mws=44300.0,
        sync_mw=20000.0,
        gen_mw=7000.0,
        load_mw=10000.0,
        nonsync_mw=0.0,
        zone_load_mw={},
        edac={},
    )
    curve = simulate_island(island, Params(horizon_s=1.0)).curve
    t, f = curve[1]
    assert (F0 - f) / t == pytest.approx(1.69, abs=0.08)


def test_edac_totals_match_the_25f_report():
    low = sum(r[0] for rows in CENTRO_SUR_ZONES.values() for r in rows)
    high = sum(r[1] for rows in CENTRO_SUR_ZONES.values() for r in rows)
    assert low == pytest.approx(1139, abs=5) and high == pytest.approx(2053, abs=10)
    tables = edac_tables({"centro_sur": 8000.0, "norte_grande": 1500.0}, 9500.0)
    # the six frequency steps of the centro-sur table; the extreme-contingency EDAC is not modelled
    assert len(tables["centro_sur"]) == 6 and len(tables["norte_grande"]) == 7


def test_secure_base_case_has_no_cascade():
    timeline = run_cascade_workflow(_toy_net(), _toy_point(), [])
    assert timeline["summary"]["stages"] == 0 and timeline["summary"]["load_shed_mw"] == 0
    assert timeline["summary"]["failure_cost_usd"] == 0


def test_overload_cascade_darkens_the_grid():
    # cutting A-C forces all 300 MW through A-B (cap 200, limit 240): it opens and nothing is left
    timeline = run_cascade_workflow(_toy_net(), _toy_point(), ["R1"], CascadeParams())
    kinds = [e["type"] for e in timeline["events"]]
    assert kinds[0] == "line_cut" and "line_overload_open" in kinds and "island_blackout" in kinds
    assert timeline["summary"]["load_shed_mw"] == 300 and timeline["summary"]["people_without_power"] == 2000
    # a total blackout: dark MW x 7.34 h of black start [44] x 8.79 US$/kWh (CNE [19]) x 1.375 for a full blackout [44]
    assert timeline["summary"]["dark_load_mw"] == 300
    assert timeline["summary"]["unserved_energy_mwh"] == pytest.approx(300 * 7.34)
    assert timeline["summary"]["failure_cost_usd"] == pytest.approx(
        300 * 7.34 * 1000 * 8.79 * 1.375, rel=1e-6
    )
    assert timeline["summary"]["cost_per_hour_usd"] == pytest.approx(300 * 1000 * 8.79 * 1.375, rel=1e-6)
    assert timeline["summary"]["outage_duration_h"] == {"value": 7.34, "is_assumption": False}


def test_load_shed_in_a_surviving_island_costs_an_hour_and_no_blackout_premium():
    from cascadasen.domain.cascade.engine import failure_cost

    shed = failure_cost(100.0, 0.0, 1000.0)
    assert shed["failure_cost_usd"] == pytest.approx(100 * 1.0 * 1000 * 8.79)
    dark = failure_cost(
        100.0, 100.0, 1000.0
    )  # same MW, but dark: black start and 10 % of the blackout premium
    assert dark["failure_cost_usd"] == pytest.approx(100 * 7.34 * 1000 * 8.79 * (1 + 0.375 * 0.1), rel=1e-6)


def test_cut_that_the_network_absorbs_sheds_nothing():
    net = _toy_net(caps=(400.0, 400.0, 400.0))
    timeline = run_cascade_workflow(net, _toy_point(), ["R1"])
    assert timeline["summary"]["load_shed_mw"] == 0 and timeline["summary"]["stages"] == 0


def test_unknown_line_is_rejected():
    with pytest.raises(ValueError):
        run_cascade_workflow(_toy_net(), _toy_point(), ["nope"])


@pytest.mark.skipif(not (PROCESSED / "baseline_opf.json").exists(), reason="processed data not built")
def test_real_grid_base_case_is_secure_and_a_cut_is_bounded():
    net, point = load_network_and_point(PROCESSED, "feb2025-1500")
    assert net.size == 188 and len(net.lines) == 273  # the 2029 links are left out of a 2025 network
    base = run_cascade_workflow(net, point, [])
    assert base["summary"]["stages"] == 0
    cut = run_cascade_workflow(net, point, [net.lines[0].id])
    assert 0 <= cut["summary"]["people_without_power"] <= point.people.sum() + 1
    assert cut["summary"]["load_shed_mw"] <= point.load.sum() + 1e-6


def test_running_state_options_for_the_strategic_theatre():
    """run_cascade_state: lines already open make no cut event, EDAC zones can be off, extra reserve
    helps an island in deficit, and the default call equals run_cascade_workflow."""
    from cascadasen.domain.cascade.engine import run_cascade_state

    net = _toy_net(caps=(400.0, 400.0, 400.0))
    deficit = _toy_point(gen=(300.0, 0.0, 0.0), load=(0.0, 225.0, 225.0))
    plain, _ = run_cascade_state(net, deficit, [])
    assert plain == run_cascade_workflow(net, deficit, [])
    assert any(e["type"] == "load_shed" for e in plain["events"])  # EDAC acts on the 150 MW deficit

    def min_hz(tl):
        return min(i["min_hz"] for i in tl["summary"]["islands"] if i["min_hz"] is not None)

    off, _ = run_cascade_state(net, deficit, [], edac_off={"centro_sur", "norte_grande"})
    assert not any(e["type"] == "load_shed" for e in off["events"])
    assert min_hz(off) < min_hz(plain)  # without EDAC the frequency falls further

    helped, _ = run_cascade_state(net, deficit, [], extra_reserve_by_bus=np.array([200.0, 0.0, 0.0]))
    assert min_hz(helped) > min_hz(plain)
    assert helped["summary"]["load_shed_mw"] <= plain["summary"]["load_shed_mw"]

    reopened, state = run_cascade_state(net, _toy_point(), [], open_lines={"R1"})
    assert not any(e["type"] == "line_cut" for e in reopened["events"]) and "R1" in state.open_lines


def _deficit_island(**kw) -> IslandInput:
    base = dict(
        inertia_mws=20000.0,
        sync_mw=6000.0,
        gen_mw=7000.0,
        load_mw=8000.0,
        nonsync_mw=1000.0,
        zone_load_mw={},
        edac={},
    )
    base.update(kw)
    return IslandInput(**base)


def test_initial_rocof_uses_the_inertia_left_after_a_trip():
    # f0 * dP / (2E): a unit that trips before the transient is already out of E, so the slope is steeper
    before = simulate_island(_deficit_island(inertia_mws=30000.0), Params(horizon_s=0.5))
    after = simulate_island(_deficit_island(inertia_mws=20000.0), Params(horizon_s=0.5))
    assert before.rocof_hz_s == pytest.approx(-50.0 * 1000.0 / 60000.0, abs=1e-3)
    assert after.rocof_hz_s == pytest.approx(-50.0 * 1000.0 / 40000.0, abs=1e-3)
    assert after.inertia_mws == 20000.0


def test_battery_waits_its_delay_then_ramps_to_full_power():
    from cascadasen.domain.cascade.frequency import battery_output

    p = Params()
    assert battery_output(None, 100.0, p) == 0.0
    assert battery_output(0.2, 100.0, p) == 0.0  # still inside the 200 ms delay
    assert battery_output(0.35, 100.0, p) == pytest.approx(50.0)
    assert battery_output(0.5, 100.0, p) == pytest.approx(100.0)  # full after delay + 300 ms ramp
    plain = simulate_island(_deficit_island())
    helped = simulate_island(_deficit_island(battery_mw=500.0))
    assert helped.min_hz > plain.min_hz and helped.battery_mw == pytest.approx(500.0)


def test_reserve_follows_the_droop_and_saturates_at_the_cap():
    # cap = 4 % of 6,000 MW = 240 MW; with R = 5 % the governors give 6,000 / 2.5 = 2,400 MW per Hz
    small = simulate_island(_deficit_island(gen_mw=7900.0))
    assert small.reserve_mw == pytest.approx(2400.0 * (50.0 - small.final_hz), rel=0.05)
    assert small.reserve_mw < 240.0
    big = simulate_island(_deficit_island(gen_mw=7700.0))
    assert big.reserve_mw == pytest.approx(240.0, rel=0.02)


def test_deployed_reserve_stays_synchronous():
    from cascadasen.domain.cascade.engine import run_cascade_state

    net = _toy_net(caps=(400.0, 400.0, 400.0))
    deficit = _toy_point(gen=(300.0, 0.0, 0.0), load=(0.0, 160.0, 160.0))
    _, state = run_cascade_state(net, deficit, [])
    assert state.gen.sum() > 300.0  # reserve was deployed
    assert state.sync.sum() == pytest.approx(state.gen.sum())  # and it is all synchronous (no solar here)


def test_islands_carry_rocof_inertia_and_bus_indices():
    from cascadasen.domain.cascade.engine import run_cascade_state

    net = _toy_net(caps=(400.0, 400.0, 400.0))
    timeline, state = run_cascade_state(net, _toy_point(gen=(300.0, 0.0, 0.0), load=(0.0, 160.0, 160.0)), [])
    isl = timeline["summary"]["islands"][0]
    assert isl["inertia_mws"] == 30000 and isl["rocof_hz_s"] < 0 and isl["final_hz"] < 50.0
    assert state.islands[0]["bus_idx"] == [0, 1, 2]


@pytest.mark.skipif(not (PROCESSED / "baseline_opf.json").exists(), reason="processed data not built")
def test_25f_prefault_split_matches_the_cen_report():
    """docs/plan.md V1 on the 188-bus network: ~1,800 MW on the 500 kV line and ~314 MW on 220 kV (+-15 %).
    Not hand-tuned: PyPSA-CL reactances and the secure base case of Feb 2025 15:00."""
    from cascadasen.domain.cascade.engine import boundary_lines

    net, point = load_network_and_point(PROCESSED, "feb2025-1500")
    flows = dc_flow(net, set(), point.gen - point.load, find_islands(net, set()))
    pos = {ln.id: k for k, ln in enumerate(net.lines)}
    kv = {ln.id: ln.kv for ln in net.lines}
    by_kv = {500.0: 0.0, 220.0: 0.0}
    for lid, sign in boundary_lines(net):
        if kv[lid] in by_kv:
            by_kv[kv[lid]] += sign * flows[pos[lid]]
    assert by_kv[500.0] == pytest.approx(1800.0, rel=0.15)
    assert by_kv[220.0] == pytest.approx(314.0, rel=0.15)


@pytest.mark.skipif(not (PROCESSED / "baseline_opf.json").exists(), reason="processed data not built")
def test_inertia_falls_with_solar():
    _, noon = load_network_and_point(PROCESSED, "nov2026-1300")
    _, evening = load_network_and_point(PROCESSED, "nov2026-2000")
    assert noon.inertia_mws.sum() < 0.8 * evening.inertia_mws.sum()


@pytest.mark.skipif(not (PROCESSED / "baseline_opf.json").exists(), reason="processed data not built")
def test_loaded_25f_corridor_cut_collapses_both_ends_by_voltage():
    """stack.md 4.6: separating the 25F corridor with more than 1,600 MW N->S before the fault collapses the islands at
    both ends by voltage. At 03:00 the corridor flows S->N below 1,000 MW: the frequency verdict stands."""
    net, point = load_network_and_point(PROCESSED, "feb2025-1500")
    loaded = run_cascade_workflow(net, point, ["R239"])
    assert loaded["summary"]["prefault_boundary_mw"] > 1600
    voltage = [
        e for e in loaded["events"] if e["type"] == "island_blackout" and e["params"]["reason"] == "voltage"
    ]
    assert len(voltage) == 2
    assert loaded["summary"]["load_shed_mw"] == loaded["summary"]["load_total_mw"]  # the whole SEN goes dark
    net3, night = load_network_and_point(PROCESSED, "feb2025-0300")
    light = run_cascade_workflow(net3, night, ["R239"])
    assert all(
        e["params"].get("reason") != "voltage" for e in light["events"] if e["type"] == "island_blackout"
    )


def test_cascade_parameters_carry_provenance(tmp_path):
    from cascadasen.domain.cascade.frequency import cascade_params
    from cascadasen.domain.simulation.params import ParameterError, collect_provenance, load_params

    records = collect_provenance(cascade_params())
    assert records and all(r.source or r.is_assumption for r in records)
    (tmp_path / "bad.yaml").write_text("frequency:\n  f0_hz: 50.0\n", encoding="utf-8")
    with pytest.raises(ParameterError):
        load_params("bad", tmp_path)
