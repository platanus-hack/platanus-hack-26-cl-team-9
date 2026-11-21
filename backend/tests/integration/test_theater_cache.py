"""Offline fallback for mapa 3: precomputed theatre runs with an index the viewer can read."""

import json

from cascadasen.application.simulation_service import SimulationService
from cascadasen.sim_fixtures import build_theater_cache


def test_theater_cache_writes_index_networks_and_runs(tmp_path, toy_network, toy_world):
    sim = SimulationService(toy_network, world=toy_world)
    build_theater_cache(sim, tmp_path, ["nov2026-1300"], seed=7, campaign=False, template="open_field")
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["points"] == ["nov2026-1300"] and len(index["runs"]) == 3
    net = json.loads((tmp_path / "network-nov2026-1300.json").read_text())
    run = json.loads((tmp_path / index["runs"][0]["file"]).read_text())
    assert {"run", "recipe", "snapshots", "report", "after_action"} <= set(run)
    assert run["recipe"]["config"]["seed"] == 7
    buses = {n["id"] for n in net["nodes"]}
    assert all(set(s["grid"]["dark"]) <= buses for s in run["snapshots"])
