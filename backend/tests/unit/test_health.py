"""Health index (docs/health.md): margins, the minimum rule and the event margins on synthetic summaries."""

from __future__ import annotations

import json

import numpy as np
import pytest

from cascadasen.domain.cascade import health
from cascadasen.domain.cascade.health import (
    HealthReport,
    Margin,
    corridor_margin,
    event_margins,
    event_report,
    inertia_margin,
    n1_cost,
    n1_margins,
    prefault_health,
)
from cascadasen.domain.cascade.network import Line, ReducedNetwork
from cascadasen.domain.cascade.scenario import OperatingPoint

USD_PER_MW = 4.0 * 1000 * 8.79  # 4 h assumed outage x CNE failure cost [19]


def _m(key: str, raw: float, in_index: bool = True) -> Margin:
    return Margin(key, key, raw, "", "", in_index=in_index)


def test_margin_clips_to_unit_range_and_keeps_raw():
    over = _m("a", -0.38)
    assert over.value == 0.0
    assert over.as_dict()["raw"] == -0.38
    assert _m("b", 1.6).value == 1.0


def test_index_is_the_minimum_of_counted_margins():
    report = HealthReport("prefault", "x", [_m("a", 0.9), _m("b", 0.2), _m("c", 0.5)])
    assert report.index == pytest.approx(0.2)
    assert report.binding == "b"
    assert report.mean == pytest.approx((0.9 + 0.2 + 0.5) / 3)


def test_margins_outside_the_index_are_reported_but_not_counted():
    report = HealthReport("prefault", "x", [_m("a", 0.9), _m("info", 0.0, in_index=False)])
    assert report.index == pytest.approx(0.9)
    assert report.binding == "a"
    assert {m["key"] for m in report.as_dict()["margins"]} == {"a", "info"}


def test_corridor_margin_uses_the_limit_of_each_direction():
    assert corridor_margin(800.0).raw == pytest.approx(0.5)  # 1,600 MW north to south
    assert corridor_margin(-500.0).raw == pytest.approx(0.5)  # 1,000 MW south to north
    assert corridor_margin(2209.0).value == 0.0
    assert corridor_margin(2209.0).raw < 0


def test_inertia_margin_spans_the_assumed_range():
    assert inertia_margin(31000.0).raw == pytest.approx(0.0)
    assert inertia_margin(42400.0).raw == pytest.approx(1.0)
    assert inertia_margin(49000.0).value == 1.0


def test_n1_security_counts_cuts_without_effect_and_worst_stays_out_of_the_index():
    secure, worst = n1_margins([("R1", 0.0), ("R2", 0.0), ("R3", 500.0), ("R4", 2000.0)], 10000.0)
    assert secure.raw == pytest.approx(0.5)
    assert worst.raw == pytest.approx(0.8)
    assert secure.in_index and not worst.in_index


def _summary(shed: float, islands: list[dict]) -> dict:
    return {"load_total_mw": 10000.0, "load_shed_mw": shed, "islands": islands}


def test_event_margins_take_the_worst_island_frequency():
    islands = [
        {"result": "maintains", "min_hz": 50.0},
        {"result": "maintains", "min_hz": 48.5},
        {"result": "dark", "min_hz": None},
    ]
    margins, uncertain = event_margins(_summary(1000.0, islands))
    by_key = {m.key: m for m in margins}
    assert by_key["supply"].raw == pytest.approx(0.9)
    assert by_key["frequency_islands"].raw == pytest.approx((48.5 - 47.5) / 1.5)
    assert not uncertain


def test_event_margins_voltage_collapse_scores_zero_and_is_uncertain():
    islands = [
        {"result": "blackout", "min_hz": None, "reason": "voltage"},
        {"result": "maintains", "min_hz": 49.9},
    ]
    margins, uncertain = event_margins(_summary(2000.0, islands))
    assert {m.key: m for m in margins}["frequency_islands"].value == 0.0
    assert uncertain


def test_event_margins_blackout_island_scores_zero():
    margins, _ = event_margins(_summary(8000.0, [{"result": "blackout", "min_hz": 47.4}]))
    assert {m.key: m for m in margins}["frequency_islands"].value == 0.0


def test_event_cost_follows_the_supply_margin_when_supply_binds():
    islands = [{"result": "maintains", "min_hz": 49.95}]
    report = event_report(_summary(3000.0, islands), "x", ["R1"])
    supply = {m.key: m for m in report.margins}["supply"]
    assert report.binding == "supply"
    cost = report.as_dict()["cost"]
    assert cost["cost_usd"] == pytest.approx((1 - supply.raw) * 10000.0 * 4.0 * 1000 * 8.79)
    assert cost["outage_duration_h"] == {"value": 4.0, "is_assumption": True}
    assert not cost["voltage_rule"]


def test_event_cost_flags_islands_darkened_by_the_voltage_rule():
    islands = [{"result": "blackout", "min_hz": None, "reason": "voltage"}]
    cost = event_report(_summary(2000.0, islands), "x", ["R1"]).extra["cost"]
    assert cost["voltage_rule"]
    assert cost["cost_usd"] == pytest.approx(2000.0 * USD_PER_MW)


def test_n1_cost_gives_expected_worst_and_a_band_without_ids():
    results = [("R1", 0.0), ("R2", 0.0), ("R3", 100.0), ("R4", 300.0)]
    cost = n1_cost(results)
    assert cost["n1_expected_cost_usd"] == pytest.approx(400.0 * USD_PER_MW / 4)
    assert cost["n1_worst_cost_usd"] == pytest.approx(300.0 * USD_PER_MW)
    assert cost["n1_cuts"] == 4 and cost["n1_cuts_with_cost"] == 2
    assert cost["n1_cost_share"] == {"count": 4, "share_band": "80-100 %"}
    assert cost["is_assumption"]
    assert not any(rid in str(cost) for rid, _ in results)


def _toy() -> tuple[ReducedNetwork, OperatingPoint]:
    lines = [Line("R0", 0, 1, 400.0, 0.01, 220, ("ab",), ()), Line("R1", 0, 2, 400.0, 0.01, 220, ("ac",), ())]
    net = ReducedNetwork(
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
    gen, load = np.array([300.0, 0, 0]), np.array([0.0, 150.0, 150.0])
    op = OperatingPoint(
        "toy", "toy", load, gen, gen.copy(), np.array([30000.0, 0, 0]), np.array([0, 1e3, 1e3])
    )
    return net, op


def test_prefault_health_reuses_given_n1_results_without_new_runs(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("no cut must run when n1_results is given")

    monkeypatch.setattr(health, "run_cascade_workflow", boom)
    net, op = _toy()
    report = prefault_health(net, op, n1_results=[("R0", 150.0), ("R1", 0.0)])
    cost = report.as_dict()["cost"]
    assert cost["n1_worst_cost_usd"] == pytest.approx(150.0 * USD_PER_MW)
    assert cost["n1_expected_cost_usd"] == pytest.approx(75.0 * USD_PER_MW)


def test_cache_writes_health_json_and_event_health_without_extra_runs(tmp_path, monkeypatch):
    from cascadasen.application import cache_builder

    net, op = _toy()
    monkeypatch.setattr(cache_builder, "load_network_and_point", lambda *_: (net, op))
    calls = []
    real = cache_builder.run_cascade_workflow
    monkeypatch.setattr(cache_builder, "run_cascade_workflow", lambda *a: calls.append(a) or real(*a))
    cache_builder._build_point(tmp_path, tmp_path, {"id": "toy", "year": 2026})
    prefault = json.loads((tmp_path / "toy" / "health.json").read_text())
    assert prefault["kind"] == "prefault" and "n1_expected_cost_usd" in prefault["cost"]
    cut = json.loads((tmp_path / "toy" / "R0.json").read_text())
    assert cut["health"]["kind"] == "event"
    assert cut["health"]["cost"]["cost_usd"] == cut["summary"]["failure_cost_usd"]
    # baseline + one run per line + one per substation: health.json adds none
    assert len(calls) == 1 + len(net.lines) + net.size
