"""The health index separates the 25F reference from a healthy operating point of the same network
(docs/health.md): `feb2025-1500` (25F) against `feb2025-0300` (minimum demand), before and after cutting R239."""

import pytest

from cascadasen.application.grid_health import DEFAULT_CUT, compare_workflow
from cascadasen.infrastructure.settings import get_settings

PROCESSED = get_settings().processed_dir
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
