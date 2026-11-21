"""Validation cases V1-V10 (docs/plan.md section 5) on the real snapshot.

Mapping used here (documented in docs/strategy.md and the defence YAML):
- V3a = scenario 25F, defences `implemented_dec2025` (north defence scheme at 0.23 s), per code.
- V3b = scenario 25F, defences `25F` (no north defence scheme), per code.
- V4/V5 = scenario 25F, defences `25F`, as it happened.
- V7/V8 = `low_demand_2026`, defences `design_2026`, 3,000 MW of synchronous generation lost pro rata.
- V10 = `midday_2026`, 103 MW of solar lost in A01 (Huatacondo, Tarapacá).
Calibrated parameters say which case they were fit on (`is_assumption` + note in params/*.yaml).
"""

from dataclasses import replace

import pytest

from cascadasen.domain.simulation.consequence import consequence_level
from cascadasen.domain.simulation.defenses import DefenseSet
from cascadasen.domain.simulation.engine import Change, run_transient
from cascadasen.domain.simulation.grid import Physics, build_state
from cascadasen.domain.simulation.network import build_reduced_network
from cascadasen.domain.simulation.powerflow import dc_flow
from cascadasen.infrastructure.settings import get_settings
from cascadasen.infrastructure.snapshot_repository import JsonSnapshotRepository

SNAP = JsonSnapshotRepository(get_settings().snapshot_path).load()
pytestmark = pytest.mark.skipif(SNAP is None, reason="run cascadasen-build first")
PH = Physics.load()
CUT_25F = [Change("open_corridor", "A06-A07/500")]


@pytest.fixture(scope="module")
def net():
    return build_reduced_network(SNAP)


@pytest.fixture(scope="module")
def s25(net):
    return build_state(net, "25F", PH)


def _run(net, state, changes, defenses, **kw):
    return run_transient(
        net, state, changes, DefenseSet.load(defenses) if isinstance(defenses, str) else defenses, PH, **kw
    )


def _south(res):
    return next(r for r in res.islands if "A07" in r.areas)


def _north(res):
    return next(r for r in res.islands if "A06" in r.areas)


def test_v1_25f_flow_split(net, s25):
    f = dc_flow(net, s25)
    assert f["A06-A07/500"] == pytest.approx(1800, rel=0.15)
    assert f["A06-A07/220"] == pytest.approx(314, rel=0.15)


def test_v2_opening_the_25f_corridor_forms_the_two_islands(net, s25):
    res = _run(net, s25, CUT_25F, "25F", scenario="25F", full=False)
    assert sorted(r.areas[0] for r in res.islands) == ["A01", "A07"]
    assert _north(res).areas[-1] == "A06" and _south(res).areas[0] == "A07"


def test_v3a_25f_with_north_defence_scheme_per_code(net, s25):
    res = _run(net, s25, CUT_25F, "implemented_dec2025", scenario="25F", full=False)
    south = _south(res)
    assert res.weak_links[0][1] == pytest.approx(0.23)
    assert south.result == "maintains"
    assert south.trace.f_min == pytest.approx(48.5, abs=0.3)
    assert south.trace.shed_mw == pytest.approx(1467.8, rel=0.20)


def test_v3b_without_north_defence_scheme_per_code(net, s25):
    south = _south(_run(net, s25, CUT_25F, "25F", scenario="25F", full=False))
    assert south.result == "maintains"
    assert south.trace.shed_mw == pytest.approx(2040.7, rel=0.20)


def test_v4_25f_as_it_happened_blackout(net, s25):
    res = _run(net, s25, CUT_25F, "25F", scenario="25F", behavior="as_happened", full=False)
    south = _south(res)
    assert south.result == "blackout"
    assert south.trace.blackout_t == pytest.approx(4.6, abs=1.0)
    assert consequence_level(res.islands, res.load_lost_mw)[0] == "L3"


def test_v5_north_after_separation(net, s25):
    north = _north(_run(net, s25, CUT_25F, "25F", scenario="25F", full=True))
    assert north.result == "maintains"
    assert north.trace.f_end == pytest.approx(51.3, abs=0.3)


@pytest.mark.skip(reason="needs the CEN classification of the seven north 500 kV segments [5]")
def test_v6_north_corridor_segments():
    """Five 'total blackout risk', two 'partial' without the defence scheme (independent test)."""


def _v7_changes(state, net):
    sync = {a: state.sync_gen(a) for a in net.order}
    total = sum(sync.values())
    return [Change("trip_gen", a, mw=3000 * sync[a] / total) for a in net.order if sync[a] > 0]


def test_v7_low_demand_2026_loss_of_3000_mw(net):
    lo = build_state(net, "low_demand_2026", PH)
    island = _run(net, lo, _v7_changes(lo, net), "design_2026", full=True).islands[0]
    assert island.result == "maintains"
    assert island.trace.f_min >= 48.1
    f_500ms = next(f for t, f in island.trace.samples if t >= 0.5)
    assert (f_500ms - PH.f0) / 0.5 == pytest.approx(-2.0, abs=0.5)


def test_v8_same_with_step_3_inactive_blacks_out(net):
    lo = build_state(net, "low_demand_2026", PH)
    d = DefenseSet.load("design_2026")
    d = replace(d, edac_steps=tuple(s for i, s in enumerate(d.edac_steps) if i != 2))
    assert _run(net, lo, _v7_changes(lo, net), d, full=False).islands[0].result == "blackout"


@pytest.mark.skip(reason="needs the digitised Polpaico frequency curve (P1)")
def test_v9_polpaico_curve_rmse():
    """RMSE over 0-5 s against the recorded curve."""


def test_v10_huatacondo_103_mw_midday(net):
    md = build_state(net, "midday_2026", PH)
    res = _run(net, md, [Change("trip_gen", "A01", mw=103, tech="solar")], "design_2026", full=False)
    assert all(r.result == "maintains" for r in res.islands)
    assert consequence_level(res.islands, res.load_lost_mw)[0] in ("L0", "L1")
