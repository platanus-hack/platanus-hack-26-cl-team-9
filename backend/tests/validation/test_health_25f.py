"""The health index separates the 25F reference from a healthy operating point of the same network
(docs/health.md): `feb2025-1500` (25F) against `feb2025-0300` (minimum demand), before and after cutting R239.

Cost (docs/engine.md "Cost"): the voltage-collapse rule darkens the whole system after cutting R239. A total blackout
is valued with the black-start hours and the blackout premium of the ISCI study [44] (81,430 MWh, about US$ 984 M),
so the model's 25F lands on the study's figure by construction of those two parameters, not by tuning the engine.
"""

import pytest

from cascadasen.application.grid_health import DEFAULT_CUT, compare_workflow
from cascadasen.domain.cascade.engine import failure_cost
from cascadasen.infrastructure.settings import get_settings

PROCESSED = get_settings().processed_dir
ISCI_LOSS_25F_USD = 984e6  # [44] ISCI for Enel Foundation (datasets.md)
pytestmark = pytest.mark.skipif(
    not (PROCESSED / "operating_points.json").exists() or not (PROCESSED / "grid_snapshot.json").exists(),
    reason="needs data/processed (cascadasen-build and the data scripts)",
)


@pytest.fixture(scope="module")
def reports():
    out = compare_workflow(PROCESSED, ["feb2025-1500", "feb2025-0300"], [DEFAULT_CUT])
    return {(r.scenario, r.kind): r for r in out}


def test_25f_prefault_is_less_healthy_than_the_reference(reports):
    bad, good = reports[("feb2025-1500", "prefault")], reports[("feb2025-0300", "prefault")]
    assert bad.index < good.index


def test_25f_prefault_is_limited_by_the_corridor_beyond_its_limit(reports):
    bad = reports[("feb2025-1500", "prefault")]
    margin = {m.key: m for m in bad.margins}["transfer_25f"]
    assert bad.binding == "transfer_25f"
    assert margin.raw < 0  # 2,209 MW north to south against 1,600 MW


def test_reference_prefault_keeps_room_on_the_corridor(reports):
    margin = {m.key: m for m in reports[("feb2025-0300", "prefault")].margins}["transfer_25f"]
    assert margin.raw > 0


def test_25f_after_the_cut_is_less_healthy_and_uncertain(reports):
    bad, good = reports[("feb2025-1500", "event")], reports[("feb2025-0300", "event")]
    assert bad.index < good.index
    assert bad.uncertain
    assert not good.uncertain


def test_25f_cut_cost_matches_the_isci_study(reports):
    cost = reports[("feb2025-1500", "event")].extra["cost"]
    print(f"\n25F R239: US$ {cost['cost_usd'] / 1e6:.1f} M, {cost['unserved_energy_mwh']:.0f} MWh")
    assert cost["cost_usd"] == pytest.approx(ISCI_LOSS_25F_USD, rel=0.01)
    assert cost["unserved_energy_mwh"] == pytest.approx(81430, rel=0.01)
    assert cost[
        "voltage_rule"
    ]  # the islands go dark by the voltage-collapse rule, not by a computed collapse


def test_a_full_blackout_without_the_split_pays_no_premium(reports):
    total_mw = 11096.0  # load of feb2025-1500 (docs/health.md)
    assert failure_cost(total_mw)["failure_cost_usd"] == pytest.approx(
        total_mw * 7.34 * 1000 * 8.79, rel=1e-6
    )
    assert failure_cost(total_mw, total_mw, total_mw)["failure_cost_usd"] == pytest.approx(
        ISCI_LOSS_25F_USD, rel=0.01
    )


def test_n1_cost_before_the_fault(reports):
    cost = reports[("feb2025-1500", "prefault")].extra["cost"]
    print(
        f"\n25F N-1: expected US$ {cost['n1_expected_cost_usd'] / 1e6:.1f} M, "
        f"worst US$ {cost['n1_worst_cost_usd'] / 1e6:.1f} M, {cost['n1_cuts_with_cost']} of {cost['n1_cuts']}"
    )
    assert cost["n1_cuts"] == 273
    assert 0 < cost["n1_expected_cost_usd"] <= cost["n1_worst_cost_usd"]
    assert cost["n1_worst_cost_usd"] == pytest.approx(
        11096 * 7.34 * 1000 * 8.79, rel=0.02
    )  # N-1 money at risk: no premium
