"""Checks on the real unified snapshot (skipped when it has not been built)."""

import pytest

from cascadasen.application.grid_queries import GridQueryService
from cascadasen.domain.naming import norm
from cascadasen.infrastructure.settings import get_settings
from cascadasen.infrastructure.snapshot_repository import JsonSnapshotRepository

SNAP = JsonSnapshotRepository(get_settings().snapshot_path).load()
pytestmark = pytest.mark.skipif(SNAP is None, reason="run cascadasen-build first")


@pytest.fixture(scope="module")
def q():
    return GridQueryService(SNAP)


def test_no_failed_checks():
    failed = [c["title"] for c in SNAP.stats["validation"]["checks"] if c["status"] == "fail"]
    assert not failed


def test_25f_corridor_is_500kv_with_parallel_220kv(q):
    """Nueva Maitencillo - Nueva Pan de Azúcar 500 kV, the line lost on 25 Feb 2025, plus its 220 kV link."""
    npa = q.list_nodes(q="NUEVA PAN DE AZUCAR", kind="substation")[1][0]["id"]
    nm = q.list_nodes(q="NUEVA MAITENCILLO", kind="substation")[1][0]["id"]
    direct = [e for e in q.list_edges(node=npa, kv_min=500)[1] if nm in (e["source"], e["target"])]
    assert direct and 1500 <= direct[0]["s_nom_mva"] <= 3000
    # without the 500 kV line the north and centre stay connected only through 220 kV
    r = q.islands([direct[0]["id"]])
    assert r["new_islands"] == 0


def test_backbone_spans_the_country(q):
    path = q.path(
        q.list_nodes(q="PARINACOTA", kind="substation")[1][0]["id"],
        q.list_nodes(q="CHILOE", kind="substation")[1][0]["id"],
    )
    assert path["found"] and path["km"] > 2000


def test_population_and_capacity_totals():
    assert abs(sum(c.population for c in SNAP.comunas) - 18_480_432) < 1000
    assert 30_000 < SNAP.stats["mw_operating_sen"] < 45_000


def test_25f_islanding_needs_the_whole_atacama_coquimbo_cut(q):
    """The north only separates when the 500 kV line, both 220 kV circuits around Punta Colorada and the
    coastal 110 kV path open together (25F: islanding came after the 220 kV protections operated)."""

    def edge(name_part, kv):
        key = norm(name_part)
        hits = [
            e
            for e in q.list_edges(q=name_part, kind="line", limit=50)[1]
            if e["kv"] == kv and norm(e["name"]).startswith(key)
        ]
        assert hits, name_part
        return hits[0]["id"]

    cut = [
        edge("NUEVA MAITENCILLO - NUEVA PAN DE AZUCAR", 500),
        edge("NUEVA PAN DE AZUCAR - PUNTA COLORADA", 220),
        edge("NUEVA MAITENCILLO - PUNTA COLORADA", 220),
        edge("PAN DE AZUCAR - PUNTA COLORADA", 220),
    ]
    assert q.islands(cut)["new_islands"] == 0  # the 110 kV coastal path still ties both sides
    r = q.islands([*cut, edge("MAITENCILLO - ALGARROBO", 110)])
    assert r["new_islands"] >= 1
    north = r["islands"][1] if "NG" in r["islands"][1]["macro_zones"] else r["islands"][0]
    assert "NG" in north["macro_zones"] and north["generation_mw"] > 5000
