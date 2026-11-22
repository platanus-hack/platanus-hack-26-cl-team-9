"""Golden bytes of the mapa 3 network JSON: `web/public/cache/network-<year>.json` and `<point>/buses.json`
(cache_builder) and `GET /sim/network` (theater_network_view) share one builder."""

import hashlib

from cascadasen.application.simulation_service import theater_network_view
from cascadasen.domain.cascade.network_json import mapa3_network
from cascadasen.domain.serialization import dumps_compact

NETWORK_SHA = "9be01eec31f8a1886a3adfd8725505717865094bfeffdd9e301628b9f78ca259"
BUSES_SHA = "2607abe134a00b91bf8d2582e1ab152ba15d03a779601def9ff16c22411bd933"
VIEW_SHA = "528d5c9b7cc582acbcda2566e0d1a110e536f874076f0c6ddfa83cd091aea43e"


def sha(obj):
    return hashlib.sha256(dumps_compact(obj).encode()).hexdigest()


def cache_files(net, op):
    base = mapa3_network(net.buses, op)
    return {k: base[k] for k in ("nodes", "lines")}, base["buses"]


def test_cache_network_and_buses_keep_their_bytes(toy_world):
    net, op = toy_world.load("nov2026-1300")
    network, buses = cache_files(net, op)
    assert list(network) == ["nodes", "lines"]
    assert list(network["nodes"][0]) == ["id", "name", "lon", "lat", "kv", "zone", "map_nodes"]
    assert list(network["lines"][0]) == ["id", "a", "b", "kv", "capacity_mw", "x_pu", "map_edges", "branches"]
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
