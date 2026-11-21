"""Criticality of a substation: what dies without backup when it falls, not how many lines it has."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cascadasen.domain.cascade.criticality import band_of, criticality_workflow, score_of
from cascadasen.domain.cascade.network import Line, ReducedNetwork
from cascadasen.domain.cascade.scenario import OperatingPoint, load_network_and_point

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"


def _net(lines: list[Line]) -> ReducedNetwork:
    return ReducedNetwork(
        names=["A", "B", "C"], lat=[-33.0] * 3, lon=[-70.0] * 3, kv=[220.0] * 3,
        model_buses=[["A_220"], ["B_220"], ["C_220"]], map_nodes=[[], [], []], lines=lines,
        index={"A": 0, "B": 1, "C": 2}, bus_of_model_bus={"A_220": 0, "B_220": 1, "C_220": 2},
    )


def _point(gen, load, people) -> OperatingPoint:
    gen, load = np.array(gen, dtype=float), np.array(load, dtype=float)
    return OperatingPoint("toy", "toy", load, gen, gen.copy(), gen * 100.0, np.array(people, dtype=float))


def test_a_chain_has_no_backup_and_a_mesh_does():
    chain = _net([Line("R0", 0, 1, 500.0, 0.01, 220, ("ab",), ()), Line("R1", 1, 2, 500.0, 0.01, 220, ("bc",), ())])
    mesh = _net([
        Line("R0", 0, 1, 500.0, 0.01, 220, ("ab",), ()),
        Line("R1", 1, 2, 500.0, 0.01, 220, ("bc",), ()),
        Line("R2", 0, 2, 500.0, 0.01, 220, ("ac",), ()),
    ])
    point = _point(gen=(100, 0, 0), load=(0, 0, 100), people=(0, 0, 5000))
    in_chain = criticality_workflow(chain, point)[1]   # B is the only path from A to C
    in_mesh = criticality_workflow(mesh, point)[1]     # B has the same two lines, but A reaches C directly
    assert in_chain["articulation"] and in_chain["isolated_mw"] == 100.0
    assert in_chain["collateral_mw"] == 100.0 and in_chain["collateral_people"] == 5000
    assert in_chain["criticality"] == 1.0 and in_chain["band"] == "alta"
    assert not in_mesh["articulation"] and in_mesh["collateral_mw"] == 0.0
    assert in_mesh["criticality"] < in_chain["criticality"]


def test_its_own_demand_does_not_count_as_collateral():
    chain = _net([Line("R0", 0, 1, 500.0, 0.01, 220, ("ab",), ()), Line("R1", 1, 2, 500.0, 0.01, 220, ("bc",), ())])
    point = _point(gen=(100, 0, 0), load=(0, 100, 0), people=(0, 3000, 0))
    result = criticality_workflow(chain, point)[1]
    assert result["own_load_mw"] == 100.0 and result["collateral_mw"] == 0.0 and result["collateral_people"] == 0


def test_score_and_bands():
    assert score_of(0.5, 0.0) == 1.0                  # half the country lost, saturated
    assert score_of(0.0, 5.0) == 0.5                  # only stress: capped at the stress weight
    assert score_of(0.0, -1.0) == 0.0
    assert [band_of(s) for s in (0.9, 0.4, 0.1, 0.01)] == ["alta", "media", "baja", "ninguna"]


def test_real_grid_degree_is_not_the_importance():
    net, point = load_network_and_point(PROCESSED, "feb2025-1500")
    rows = criticality_workflow(net, point)
    assert len(rows) > 150 and all(0.0 <= r["criticality"] <= 1.0 for r in rows.values())
    hubs = [r for r in rows.values() if r["degree"] >= 8]
    quiet_hubs = [r for r in hubs if r["criticality"] < 0.1]
    thin = [r for r in rows.values() if r["degree"] <= 2 and r["criticality"] >= 0.33]
    assert thin, "some substations with 2 lines or fewer must be critical"
    assert len(quiet_hubs) + len(thin) > 0
