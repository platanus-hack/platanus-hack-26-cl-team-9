"""The four 25F-corridor rows of docs/engine.md "Results so far" (cut R239 on the 188-bus network), pinned so an engine
change that moves them is noticed. Figures measured 2026-11-22 after the causal stages of issue #90: the people and
MW did not move, only the times after a waiting stage."""

import pytest

from cascadasen.domain.cascade.engine import run_cascade_workflow
from cascadasen.domain.cascade.scenario import load_network_and_point
from cascadasen.infrastructure.settings import get_settings

PROCESSED = get_settings().processed_dir
pytestmark = pytest.mark.skipif(
    not (PROCESSED / "baseline_opf.json").exists(), reason="needs data/processed (the data scripts)"
)


def _r239(point_id: str) -> dict:
    net, point = load_network_and_point(PROCESSED, point_id)
    return run_cascade_workflow(net, point, ["R239"])


def _voltage_times(tl: dict) -> list[float]:
    return [
        e["t"] for e in tl["events"] if e["type"] == "island_blackout" and e["params"]["reason"] == "voltage"
    ]


@pytest.mark.parametrize(
    ("point_id", "people_m", "total_mw"), [("feb2025-1500", 16.8, 11096), ("nov2026-1300", 17.0, 10836)]
)
def test_loaded_corridor_blacks_out_the_whole_system_by_voltage(point_id, people_m, total_mw):
    tl = _r239(point_id)
    s = tl["summary"]
    assert s["people_without_power"] / 1e6 == pytest.approx(people_m, abs=0.05)
    assert s["load_shed_mw"] == s["load_total_mw"] == total_mw
    assert s["stages"] == 2
    assert _voltage_times(tl) == [2.0, 2.0]


def test_night_corridor_flowing_south_to_north_has_no_voltage_collapse():
    tl = _r239("feb2025-0300")
    s = tl["summary"]
    assert s["people_without_power"] / 1e6 == pytest.approx(0.31, abs=0.01)
    assert (s["load_shed_mw"], s["load_total_mw"]) == (631, 8719)
    assert not _voltage_times(tl)


def test_evening_corridor_under_its_limit_survives_with_edac():
    """1,287 MW N->S, under the 1,600 MW limit: no voltage rule. Stage 2 splits 115 + 73 buses and the 115-bus island
    sheds EDAC steps 1-5; stage 3 waits until those end (6.48 s, was 3.0 s) and splits it again. With the default
    `resplit_memory=False` the 98-bus part fires step 1 again and holds; with it on, it collapses (14.7 M people)."""
    from cascadasen.domain.cascade.engine import CascadeParams

    tl = _r239("nov2026-2000")
    s = tl["summary"]
    assert s["people_without_power"] / 1e6 == pytest.approx(3.9, abs=0.05)
    assert (s["load_shed_mw"], s["load_total_mw"]) == (1825, 10934)
    assert s["stages"] == 3 and [f["t"] for f in tl["frames"]] == [0.0, 1.0, 2.0, 6.48]
    assert not _voltage_times(tl)
    assert not [e for e in tl["events"] if e["type"] == "island_blackout"]
    net, point = load_network_and_point(PROCESSED, "nov2026-2000")
    memory = run_cascade_workflow(net, point, ["R239"], CascadeParams(resplit_memory=True))["summary"]
    assert memory["people_without_power"] / 1e6 == pytest.approx(14.7, abs=0.05)
    assert memory["load_shed_mw"] == 6738
