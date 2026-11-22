"""Golden hashes of the cascade engine output (events, frames, summary) and of the theatre grid frame.
They pin the exact JSON, including every rounding, so a refactor of the event and frame builders
cannot change a single byte. The cascade hashes were taken from upstream/main (386a21b1 + #139) before
the refactor was re-applied on top of it. The real-network case is skipped when `data/processed` is missing."""

import hashlib
import json

import pytest

from cascadasen.domain.cascade.engine import run_cascade_workflow
from cascadasen.domain.cascade.scenario import load_network_and_point
from cascadasen.domain.theater.grid import Change, TheaterGrid
from cascadasen.infrastructure.settings import get_settings

PROCESSED = get_settings().processed_dir
HAVE_DATA = (PROCESSED / "grid_snapshot.json").exists() and (PROCESSED / "operating_points.json").exists()


def digest(*docs) -> str:
    h = hashlib.sha256()
    for d in docs:
        h.update(json.dumps(d, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()


def test_toy_cascade_and_theater_frame_are_byte_stable(toy_world):
    net, point = toy_world.load("nov2026-1300")
    lines = [ln.id for ln in net.buses.lines]
    runs = [run_cascade_workflow(net.buses, point, cut) for cut in [[], *[[x] for x in lines], lines[:2]]]
    assert digest(*runs) == TOY_CASCADE
    grid = TheaterGrid.from_point(net, point)
    grid.run_cascade(grid.apply(Change("open_corridor", "T2-T3"))[0])
    assert digest(grid.frame()) == TOY_FRAME


@pytest.mark.skipif(not HAVE_DATA, reason="run cascadasen-build first")
@pytest.mark.parametrize("point_id", ["nov2026-1300", "feb2025-0300"])
def test_real_cascade_is_byte_stable_for_every_single_cut(point_id):
    net, point = load_network_and_point(PROCESSED, point_id)
    cuts = [[], *[[ln.id] for ln in net.lines], [ln.id for ln in net.lines[:3]]]
    runs = [run_cascade_workflow(net, point, cut) for cut in cuts]
    kinds = {e["type"] for r in runs for e in r["events"]}
    assert {"line_cut", "island_formed", "line_overload_open", "load_shed", "island_stable"} <= kinds
    got = digest(*runs)
    assert got == REAL_CASCADE[point_id], f"{point_id} digest {got}"  # full value: the hash depends on the platform's floats


TOY_CASCADE = "8bdad44a1774856d155a868024abe9c30f6075b07b3d024f2203fe82d0f77ba5"
TOY_FRAME = "f88e8cbb434ac5f39a0cad24521e78d2f6c68f174380e35fd4f3a036eede2316"
REAL_CASCADE = {
    "nov2026-1300": "1d05de454ed90a80218f1735a90a17257bdfa572e76e72a9c08e34339ec39e48",
    "feb2025-0300": "31d2e13895f13ba41350d399c293afff5a6abade38d3462d9f3c5c790cba1664",
}
