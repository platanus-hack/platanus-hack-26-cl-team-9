"""Golden bytes of the mapa 3 network JSON: `web/public/cache/network-<year>.json` and `<point>/buses.json`
(cache_builder) and `GET /sim/network` (theater_network_view) share one builder. The hashes were taken from
upstream/main before the refactor (nodes and lines carry `country` there)."""

import hashlib

from cascadasen.application.simulation_service import theater_network_view
from cascadasen.domain.cascade.network_json import buses_json, network_json
from cascadasen.domain.serialization import dumps_compact

NETWORK_SHA = "f2074dbf27332733b67eb998a70f2226fe3c739c960c551e16ff779dcf7626d3"
BUSES_SHA = "2607abe134a00b91bf8d2582e1ab152ba15d03a779601def9ff16c22411bd933"
VIEW_SHA = "683b46254992112ccc70424f142e11262736f008d1a15f98467f241581358030"


def sha(obj):
    return hashlib.sha256(dumps_compact(obj).encode()).hexdigest()


def test_cache_network_and_buses_keep_their_bytes(toy_world):
    net, op = toy_world.load("nov2026-1300")
    network, buses = network_json(net.buses), buses_json(net.buses, op)
    assert list(network) == ["nodes", "lines"]
    assert list(network["nodes"][0]) == ["id", "name", "lon", "lat", "kv", "zone", "map_nodes", "country"]
    assert list(network["lines"][0]) == [
        "id",
        "a",
        "b",
        "kv",
        "capacity_mw",
        "x_pu",
        "map_edges",
        "branches",
        "country",
    ]
    assert sha(network) == NETWORK_SHA
    assert sha(buses) == BUSES_SHA


def test_theater_network_view_keeps_its_bytes(toy_world):
    net, op = toy_world.load("nov2026-1300")
    view = theater_network_view(net, op, "nov2026-1300", ["nov2026-1300"])
    assert list(view) == [
        "point",
        "points",
        "nodes",
        "lines",
        "buses",
        "areas",
        "corridors",
        "defenses",
        "zones",
    ]
    assert list(view["nodes"][0])[-1] == "area" and list(view["lines"][0])[-1] == "corridor"
    assert sha(view) == VIEW_SHA
