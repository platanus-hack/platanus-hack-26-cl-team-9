"""Health index (docs/health.md): margins, the minimum rule and the event margins on synthetic summaries."""

from __future__ import annotations

import pytest

from cascadasen.domain.cascade.health import (
    HealthReport,
    Margin,
    corridor_margin,
    event_margins,
    inertia_margin,
    n1_margins,
)


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


def _summary(shed: float, islands: list[dict], uncertain: bool = False) -> dict:
    return {"load_total_mw": 10000.0, "load_shed_mw": shed, "islands": islands, "uncertain": uncertain}


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
