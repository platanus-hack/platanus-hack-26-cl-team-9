"""Flagship experiment on the real reduced SEN (docs/strategy.md section 9): the three policies
face the same scenario and seed and must produce different, reproducible outcomes."""

import pytest

from cascadasen.domain.simulation.network import build_reduced_network
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.infrastructure.settings import get_settings
from cascadasen.infrastructure.snapshot_repository import JsonSnapshotRepository

SNAP = JsonSnapshotRepository(get_settings().snapshot_path).load()
pytestmark = pytest.mark.skipif(SNAP is None, reason="run cascadasen-build first")


@pytest.fixture(scope="module")
def reports():
    net = build_reduced_network(SNAP)
    out = {}
    for policy in ("A", "B", "C"):
        sim = Simulation(
            net,
            RunConfig(
                template="flagship_observability",
                policy=policy,
                seed=7,
                adversary=AdversaryConfig(True, "reduce_observability", 8, False),
            ),
        )
        sim.run_to_end()
        out[policy] = sim.report()
    return out


def test_policies_lead_to_different_outcomes(reports):
    mc = {p: r["indicators"]["mission_continuity"] for p, r in reports.items()}
    assert len(set(mc.values())) == 3
    assert all(0.5 < v <= 1.0 for v in mc.values())


def test_preventive_policy_pays_in_unnecessary_actions(reports):
    wrong = {p: r["indicators"]["wrong_decisions"] for p, r in reports.items()}
    assert wrong["B"] > wrong["A"] and wrong["B"] > wrong["C"]


def test_adaptive_coordination_keeps_most_of_the_mission(reports):
    """With crews on the map, the preventive policy ties local crews up in manual operation and
    segmentation, so it no longer beats the reactive one; adaptive coordination stays best."""
    mc = {p: r["indicators"]["mission_continuity"] for p, r in reports.items()}
    assert mc["C"] > mc["A"] and mc["C"] > mc["B"]


def test_reports_carry_the_notice_and_no_constraint_violation(reports):
    for r in reports.values():
        assert r["notice"].startswith("Escenario hipotético")
        assert r["coordination"]["constraint_violations"] == 0
