"""Static exports for consumers that do not call the API (the frontend MVP reads files).

data/processed/geo/<layer>.geojson   map layers
data/processed/sen_network.json      compact network for the frontend (nodes, edges, plants, zones)
data/processed/atlas_sen.html        the API test map with every layer embedded (works offline)
"""

from __future__ import annotations

import json
from pathlib import Path

from cascadasen.application.grid_queries import GridQueryService
from cascadasen.domain.model import GridSnapshot

LAYERS = ("substations", "taps", "lines", "plants", "storage", "comunas")
MAP_TEMPLATE = Path(__file__).resolve().parents[1] / "api" / "static" / "map.html"
EMBED_TAG = '<script id="sen-embed" type="application/json">null</script>'


class StaticFilesExporter:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir

    def export(self, snapshot: GridSnapshot) -> list[str]:
        q = GridQueryService(snapshot)
        geo = self.out_dir / "geo"
        geo.mkdir(parents=True, exist_ok=True)
        written = []
        for layer in LAYERS:
            path = geo / f"{layer}.geojson"
            path.write_text(
                json.dumps(q.geojson(layer), ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
            )
            written.append(str(path))
        network = {
            "version": snapshot.version,
            "built_at": snapshot.built_at,
            "description": "Red completa del SEN unificada (IDE Energía + CEN Infotecnica + PyPSA-CL + INE Censo 2024).",
            "nodes": [q.node_summary(n) for n in snapshot.nodes if n.located],
            "edges": [q.edge_summary(e) for e in snapshot.edges],
            "plants": q.list_plants(operating=True)[1],
            "zones": q.macro_zones(),
            "assumptions": snapshot.assumptions,
            "sources": q.sources(),
            "validation": q.validation(),
        }
        path = self.out_dir / "sen_network.json"
        path.write_text(json.dumps(network, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written.append(str(path))
        written.append(str(self.export_standalone_map(q)))
        return written

    def export_standalone_map(self, q: GridQueryService) -> Path:
        embed = {
            "stats": q.stats(),
            "validation": q.validation(),
            "zones": q.macro_zones(),
            "sources": q.sources(),
            "assumptions": q.s.assumptions,
            "geo": {layer: q.geojson(layer) for layer in LAYERS},
        }
        payload = json.dumps(embed, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        html = MAP_TEMPLATE.read_text(encoding="utf-8")
        if EMBED_TAG not in html:
            raise RuntimeError("map template lost its embed tag")
        path = self.out_dir / "atlas_sen.html"
        path.write_text(
            html.replace(EMBED_TAG, EMBED_TAG.replace(">null<", f">{payload}<")), encoding="utf-8"
        )
        return path
