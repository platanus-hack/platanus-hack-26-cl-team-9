"""The mapa 3 network as JSON: nodes, lines and per-bus operating point. `web/public/cache` files
(`cascadasen-cache`, `cascadasen-grids`) and `GET /sim/network` (`theater_network_view`) are all built
from these."""

from __future__ import annotations

from typing import Any

from .network import ReducedNetwork, bus_id
from .scenario import OperatingPoint


def network_json(net: ReducedNetwork) -> dict[str, Any]:
    ids = [bus_id(i) for i in range(net.size)]
    return {
        "nodes": [
            {
                "id": ids[i],
                "name": net.names[i],
                "lon": net.lon[i],
                "lat": net.lat[i],
                "kv": net.kv[i],
                "zone": net.zone(i),
                "map_nodes": net.map_nodes[i],
                "country": net.country,
            }
            for i in range(net.size)
        ],
        "lines": [
            {
                "id": ln.id,
                "a": ids[ln.a],
                "b": ids[ln.b],
                "kv": ln.kv,
                "capacity_mw": round(ln.capacity_mw, 1),
                "x_pu": ln.x_pu,
                "map_edges": list(ln.map_edges),
                "branches": list(ln.branches),
                "country": ln.country,
            }
            for ln in net.lines
        ],
    }


def buses_json(net: ReducedNetwork, op: OperatingPoint) -> dict[str, Any]:
    return {
        bus_id(i): {
            "gen_mw": round(float(op.gen[i]), 1),
            "load_mw": round(float(op.load[i]), 1),
            "people": round(float(op.people[i])),
        }
        for i in range(net.size)
    }
