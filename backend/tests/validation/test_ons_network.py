"""Brazil's flow network on disk (data/processed/latam/BRA/network.json) follows docs/network-format.md.

Skipped when it was not built (`cascadasen-regional --countries BRA --ons`)."""

import json
import statistics
from pathlib import Path

import networkx as nx
import pytest

from cascadasen.domain.validation import X_PER_KM

LATAM = Path(__file__).resolve().parents[3] / "data" / "processed" / "latam"
NETWORK = LATAM / "BRA" / "network.json"
pytestmark = pytest.mark.skipif(not NETWORK.exists(), reason="BRA/network.json not built")

MIN_COORDINATE_MATCH = 0.98
MAIN_COMPONENT_SHARE = 0.95
LENGTH_TOLERANCE = 0.15  # against the MapYourGrid figure, which was not opened (docs/regional.md section 3)


@pytest.fixture(scope="module")
def net() -> dict:
    return json.loads(NETWORK.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def flow() -> dict:
    return json.loads((LATAM / "manifest.json").read_text(encoding="utf-8"))["countries"]["BRA"]["flow"]


def test_every_element_carries_country_source_and_assumption_flag(net):
    for key in ("buses", "lines", "dc_links", "plants"):
        assert net[key], key
        for item in net[key]:
            assert item["country"] == "BRA" and item["source"], item["id"]
            assert isinstance(item["is_assumption"], bool), item["id"]
            if item.get("assumed_fields"):
                assert item["is_assumption"], item["id"]
    assert all("CC BY" in s["license"] for s in net["sources"] if s["id"].startswith("ons_"))


def test_line_parameters_are_positive_and_ends_exist(net):
    buses = {b["id"] for b in net["buses"]}
    assert len(buses) == len(net["buses"])
    for ln in net["lines"]:
        assert ln["a"] in buses and ln["b"] in buses and ln["a"] != ln["b"], ln["id"]
        assert ln["x_pu"] > 0 and ln["capacity_mw"] > 0, ln["id"]
        assert ln["kv"] >= 230, ln["id"]
    for b in net["buses"]:
        assert -34 <= b["lat"] <= 6 and -75 <= b["lon"] <= -34, b["id"]


def test_units_give_textbook_reactance_per_km(net):
    """Guard against misread ONS units: median x per circuit-km must sit in the typical range."""
    per_kv: dict[float, list[float]] = {}
    for ln in net["lines"]:
        if ln["length_km"] >= 5 and "x_pu" not in ln["assumed_fields"]:
            per_kv.setdefault(ln["kv"], []).append(ln["x_ohm"] * ln["circuits"] / ln["length_km"])
    assert per_kv
    for kv, values in per_kv.items():
        lo, hi = X_PER_KM[min(X_PER_KM, key=lambda k: abs(k - kv))]
        assert lo <= statistics.median(values) <= hi, kv


def test_one_main_connected_component(net):
    graph = nx.Graph()
    graph.add_nodes_from(b["id"] for b in net["buses"])
    graph.add_edges_from((ln["a"], ln["b"]) for ln in net["lines"])
    main = max(nx.connected_components(graph), key=len)
    assert len(main) >= MAIN_COMPONENT_SHARE * graph.number_of_nodes()


def test_length_close_to_the_official_figure(flow):
    check = flow["length_check"]
    assert abs(check["ac_vs_official"]) <= LENGTH_TOLERANCE
    assert abs(check["ac_dc_vs_official"]) <= LENGTH_TOLERANCE


def test_coordinate_match_rate(flow):
    assert flow["coordinates"]["match_rate"] >= MIN_COORDINATE_MATCH


def test_manifest_counts_match_the_file(net, flow):
    assert flow["counts"]["buses"] == len(net["buses"])
    assert flow["counts"]["lines"] == len(net["lines"])
    assert flow["counts"]["dc_links"] == len(net["dc_links"])
    assumed = sum(1 for ln in net["lines"] for c in ln["capacity_a"] if c is None)
    assert assumed == flow["assumed"]["capacity_mw"]


def test_deduction_error_is_reported(flow):
    err = flow["deduction_error"]
    assert err["x"]["all"]["n"] > 1000 and err["capacity"]["all"]["n"] > 1000
    assert 0 < err["topology"]["precision"] <= 1 and 0 < err["topology"]["recall"] <= 1
