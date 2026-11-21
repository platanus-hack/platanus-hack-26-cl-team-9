"""The regional context layer on disk (data/processed/latam) follows the common schema.

Skipped when the layer was not built (`cascadasen-regional`)."""

import json
from pathlib import Path

import pytest

LATAM = Path(__file__).resolve().parents[3] / "data" / "processed" / "latam"
pytestmark = pytest.mark.skipif(
    not (LATAM / "manifest.json").exists(), reason="data/processed/latam not built"
)


def _countries() -> list[str]:
    return sorted(json.loads((LATAM / "manifest.json").read_text())["countries"])


def _features(iso: str, layer: str) -> list[dict]:
    return json.loads((LATAM / iso / f"{layer}.geojson").read_text())["features"]


def test_every_element_carries_its_provenance():
    for iso in _countries():
        for layer in ("lines", "substations", "plants"):
            for f in _features(iso, layer):
                p = f["properties"]
                assert p["country"] == iso and p["source"] and p["source_record"], (iso, layer, p.get("id"))
                assert p["id"].startswith(iso + "-")


def test_ids_are_unique_per_country_and_layer():
    for iso in _countries():
        for layer in ("lines", "substations", "plants"):
            ids = [f["properties"]["id"] for f in _features(iso, layer)]
            assert len(ids) == len(set(ids)), (iso, layer)


def test_lines_have_voltage_and_are_transmission_level():
    for iso in _countries():
        lines = _features(iso, "lines")
        assert lines, iso
        assert all(f["properties"]["kv"] and f["properties"]["kv"] >= 66 for f in lines), iso


def test_plant_power_is_in_plausible_megawatts():
    for iso in _countries():
        for f in _features(iso, "plants"):
            assert 0 < f["properties"]["mw"] <= 15000, (
                iso,
                f["properties"]["name"],
            )  # Itaipú, 14,000 MW, is the largest


def test_manifest_lists_source_licence_and_attribution():
    manifest = json.loads((LATAM / "manifest.json").read_text())
    for iso, entry in manifest["countries"].items():
        assert entry["sources"], iso
        for s in entry["sources"]:
            assert s["license"] and s["attribution"] and s["url"], (iso, s["id"])
