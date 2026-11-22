"""The four 25F-corridor rows of docs/engine.md "Results so far" (cut R239 on the 188-bus network), pinned so an engine
change that moves them is noticed. Figures measured 2026-11-22 after issue #90: causal stages (times only), people of
dark buses counted whole (a whole-system blackout is the 18.16 M people the model assigns) and re-split islands that
keep their fired EDAC steps and deployed reserve (Nov 2026 20:00 goes from 3.9 M to 15.4 M people)."""

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
    ("point_id", "people_m", "total_mw"), [("feb2025-1500", 18.16, 11096), ("nov2026-1300", 18.16, 10836)]
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


def test_evening_corridor_under_its_limit_loses_the_re_split_island_by_frequency():
    """1,287 MW N->S, under the 1,600 MW limit: no voltage rule. Stage 2 splits 115 + 73 buses; the 115-bus island sheds
    EDAC steps 1-5 and deploys all its reserve. Stage 3 (6.48 s) cuts off 17 buses with a 342 MW surplus; the 98-bus
    rest has a 350 MW deficit, no reserve and only step 6 left, so it collapses at 25.6 s whatever the horizon
    (docs/engine.md "Results so far"). With the old double counting (`resplit_memory=False`) it held."""
    from cascadasen.domain.cascade.engine import CascadeParams
    from cascadasen.domain.cascade.frequency import Params

    tl = _r239("nov2026-2000")
    s = tl["summary"]
    assert s["people_without_power"] / 1e6 == pytest.approx(15.4, abs=0.05)
    assert (s["load_shed_mw"], s["load_total_mw"]) == (6738, 10934)
    assert s["stages"] == 3 and [f["t"] for f in tl["frames"]] == [0.0, 1.0, 2.0, 6.48]
    assert not _voltage_times(tl)
    blackouts = [e for e in tl["events"] if e["type"] == "island_blackout"]
    assert [(e["params"]["buses"], e["params"]["reason"], e["t"]) for e in blackouts] == [
        (98, "frequency", 25.62)
    ]
    net, point = load_network_and_point(PROCESSED, "nov2026-2000")
    longer = run_cascade_workflow(net, point, ["R239"], CascadeParams(frequency=Params(horizon_s=60.0)))
    assert [e["t"] for e in longer["events"] if e["type"] == "island_blackout"] == [
        pytest.approx(25.6, abs=0.05)
    ]
    old = run_cascade_workflow(net, point, ["R239"], CascadeParams(resplit_memory=False))["summary"]
    assert old["load_shed_mw"] == 1825
