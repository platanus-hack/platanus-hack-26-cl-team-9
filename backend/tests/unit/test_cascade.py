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
    assert len(tables["centro_sur"]) == 6 and len(tables["norte_grande"]) == 7


def test_secure_base_case_has_no_cascade():
    timeline = run_cascade_workflow(_toy_net(), _toy_point(), [])
    assert timeline["summary"]["stages"] == 0 and timeline["summary"]["load_shed_mw"] == 0


def test_overload_cascade_darkens_the_grid():
    # cutting A-C forces all 300 MW through A-B (cap 200, limit 240): it opens and nothing is left
    timeline = run_cascade_workflow(_toy_net(), _toy_point(), ["R1"], CascadeParams())
    kinds = [e["type"] for e in timeline["events"]]
    assert kinds[0] == "line_cut" and "line_overload_open" in kinds and "island_blackout" in kinds
    assert timeline["summary"]["load_shed_mw"] == 300 and timeline["summary"]["people_without_power"] == 2000


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
