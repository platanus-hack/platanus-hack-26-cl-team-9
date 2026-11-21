"""Flagship experiment on the mapa 3 network (docs/strategy.md section 9, docs/mapa3.md): the three
policies face the same scenario and seed and must produce different, reproducible outcomes."""

import pytest

from cascadasen.application.theater_world import ProcessedWorld
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.infrastructure.settings import get_settings

PROCESSED = get_settings().processed_dir
pytestmark = pytest.mark.skipif(
    not (PROCESSED / "operating_points.json").exists() or not (PROCESSED / "grid_snapshot.json").exists(),
    reason="needs data/processed (cascadasen-build and the data scripts)",
)


@pytest.fixture(scope="module")
def reports():
    world = ProcessedWorld(PROCESSED)
    out = {}
    for policy in ("A", "B", "C"):
        sim = Simulation(
            world,
            RunConfig(
                template="flagship_observability",
                policy=policy,
                seed=7,
                operating_point="nov2026-1300",
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
    """On the mapa 3 network with crews on the map, adaptive coordination keeps the most continuity."""
    mc = {p: r["indicators"]["mission_continuity"] for p, r in reports.items()}
    assert mc["C"] > mc["A"] and mc["C"] > mc["B"]


def test_reports_carry_the_notice_and_no_constraint_violation(reports):
    for r in reports.values():
        assert r["notice"].startswith("Escenario hipotético")
        assert r["coordination"]["constraint_violations"] == 0
