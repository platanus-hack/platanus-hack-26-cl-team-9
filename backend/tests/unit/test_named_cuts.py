from pathlib import Path

import pytest

from cascadasen.application.cache_builder import NAMED_CUTS, lines_of_substation
from cascadasen.domain.cascade.scenario import load_network_and_point

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"


def test_named_cut_takes_every_line_of_the_substation():
    net, _ = load_network_and_point(PROCESSED, "nov2026-2000")
    ids = lines_of_substation(net, NAMED_CUTS["falla-charrua-2010"])
    bus = net.index["S/E CHARRUA"]
    assert len(ids) == len({ln.id for ln in net.lines if bus in (ln.a, ln.b)}) > 2


def test_unknown_substation_raises():
    net, _ = load_network_and_point(PROCESSED, "nov2026-2000")
    with pytest.raises(ValueError):
        lines_of_substation(net, "S/E NO EXISTE")
