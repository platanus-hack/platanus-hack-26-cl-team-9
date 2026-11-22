"""The health index separates the 25F reference from a healthy operating point of the same network
(docs/health.md): `feb2025-1500` (25F) against `feb2025-0300` (minimum demand), before and after cutting R239.

Cost (ASSUMPTION, only to order magnitudes, docs/health.md "Cost"): since the voltage-collapse rule darkens the
25F islands (#76), the model loses the whole system after cutting R239 and values it at about US$ 390 M
(11,096 MW x 4 h x 8.79 US$/kWh). The press estimate of the 25F loss is US$ 984 M (datasets.md [44], not
verified); a full blackout would need about 10 h of average unserved energy to reach it. The gap comes from the
assumed 4 h duration (and from the press figure measuring more than unserved energy). These tests pin the
figures; they do not tune the duration to match.
"""

import pytest

from cascadasen.application.grid_health import DEFAULT_CUT, compare_workflow
from cascadasen.domain.cascade.engine import failure_cost
from cascadasen.infrastructure.settings import get_settings

PROCESSED = get_settings().processed_dir
PRESS_LOSS_25F_USD = 984e6  # press estimate, not verified (datasets.md [44]); never shown in the UI
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


def test_25f_cut_cost_is_the_full_blackout_of_about_390_million(reports):
    cost = reports[("feb2025-1500", "event")].extra["cost"]
    print(f"\n25F R239: US$ {cost['cost_usd'] / 1e6:.1f} M, {cost['unserved_energy_mwh']:.0f} MWh")
    assert cost["cost_usd"] == pytest.approx(390e6, rel=0.02)
    assert cost["outage_duration_h"] == {"value": 4.0, "is_assumption": True}
    assert cost[
        "voltage_rule"
    ]  # the islands go dark by the voltage-collapse rule, not by a computed collapse


def test_full_blackout_and_the_hours_behind_the_press_estimate(reports):
    total_mw = 11096.0  # load of feb2025-1500 (docs/health.md)
    blackout = failure_cost(total_mw)["failure_cost_usd"]
    hours = PRESS_LOSS_25F_USD / (total_mw * 1000 * 8.79)
    print(f"\nfull blackout 4 h: US$ {blackout / 1e6:.0f} M; US$ 984 M needs {hours:.1f} h of full blackout")
    assert blackout == pytest.approx(390e6, rel=0.02)
    assert hours == pytest.approx(10.1, abs=0.2)
    assert reports[("feb2025-1500", "event")].extra["cost"]["cost_usd"] < PRESS_LOSS_25F_USD


def test_n1_cost_before_the_fault(reports):
    cost = reports[("feb2025-1500", "prefault")].extra["cost"]
    print(
        f"\n25F N-1: expected US$ {cost['n1_expected_cost_usd'] / 1e6:.1f} M, "
        f"worst US$ {cost['n1_worst_cost_usd'] / 1e6:.1f} M, {cost['n1_cuts_with_cost']} of {cost['n1_cuts']}"
    )
    assert cost["n1_cuts"] == 273
    assert 0 < cost["n1_expected_cost_usd"] <= cost["n1_worst_cost_usd"]
    assert cost["n1_expected_cost_usd"] == pytest.approx(7.5e6, rel=0.1)
    assert cost["n1_worst_cost_usd"] == pytest.approx(390e6, rel=0.02)
