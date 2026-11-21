# CascadaSEN backend: unified grid data API

Read-only API over one graph of the Chilean grid (SEN), built from four public sources. Every node, line, plant and comuna keeps the ids it has in each source and a provenance list. Inferred values carry `is_assumption`.

## Run

```bash
cd backend
uv sync                                  # or: uv pip install -e . --group dev
uv run cascadasen-build                  # download (cached in data/raw/) and unify -> data/processed/
uv run cascadasen-build --refresh        # force a new download of every source
uv run cascadasen-api                    # http://localhost:8000/map  (docs: /docs)
uv run pytest
```

After a rebuild, `POST /api/v1/admin/reload` reloads the snapshot without restarting the server.

Build outputs in `data/processed/`:

| File | Content |
|---|---|
| `grid_snapshot.json` + `comunas_geometry.json` | Unified snapshot that the API loads |
| `geo/{substations,taps,lines,plants,storage,comunas}.geojson` | Map layers |
| `sen_network.json` | Compact network for the frontend (nodes, edges, plants, zones, validation) |
| `atlas_sen.html` | Test map with every layer embedded; works offline |

## Sources

| Adapter | Source | Provides |
|---|---|---|
| `IdeEnergiaSource` | Ministerio de Energía, IDE Energía MapServer (layers 1-6, 8, 9, 10) | Substation coordinates, line geometry, plants (MW, technology), storage |
| `InfotecnicaSource` | CEN, `api-infotecnica.coordinador.cl/v1/{subestaciones,barras,lineas,tramos,centrales}` | Official ids and codes, busbar voltages, line sections with declared end points |
| `PypsaClSource` | Ministerio de Energía, PyPSA-CL `Topology.xlsx` (public SharePoint folder) | 234 buses, 323 lines with r, x and s_nom, generator connection bus, storage |
| `IneCensoSource` | INE Censo 2024 FeatureServer (layers 11 comunas, 2 census zones) | Comuna polygons, population, households, urban census zones |

## Architecture (ports and adapters)

```
api/ (FastAPI, driving adapter) ──> application/ (BuildGridSnapshot, GridQueryService)
                                          │
                                          ▼
                                   domain/ (model, unify, topology_inference, validation, ports)
                                          ▲
infrastructure/ (sources/*, http cache, arcgis, snapshot repository, exporters, container)
```

- `domain/ports.py` defines `GridDataSource`, `SnapshotRepository` and `ContractExporter`. To add a source, write one adapter that implements `contribute(bundle, refresh)` and register it in `infrastructure/container.py`.
- `domain/unify.py` is a pure function of the `SourceBundle`. It joins substations by CEN id, infers line ends from geometry, reconciles them with the official CEN sections, attaches PyPSA-CL parameters and assigns population.
- `domain/validation.py` runs on every build. It checks national coverage, end-to-end connectivity, agreement between sources and plausible reactance per km. Results are at `GET /api/v1/validation` and in the map panel.

## Main endpoints

`/api/v1/nodes`, `/nodes/{id}` (connections, plants, storage, served comunas), `/edges`, `/edges/{id}`, `/plants`, `/storage`, `/comunas`, `/zones` (macro zones and links between them with known capacity), `/graph/path`, `POST /graph/islands` (connectivity after removing lines or nodes), `/model/buses`, `/model/branches`, `/geo/{layer}.geojson`, `/sources`, `/validation`, `/assumptions`.

## Simulation

The simulation layer sits on top of the snapshot (concepts in `docs/strategy.md`, HTTP contract in `docs/stack.md` sections 7 and 7.1).

- `domain/simulation/`: physical engine on the reduced trunk network (13 operating areas, `params/network.yaml`).
  - Modules: DC power flow (`powerflow.py`), weak-link cascade (`engine.py`), island swing-equation frequency with EDAC, extreme-contingency shedding, battery and over-frequency curtailment (`frequency.py`), consequence card L0-L3 (`consequence.py`) and the `timeline.json` contract (`timeline.py`).
  - Every parameter in `params/*.yaml` carries a `source` or `is_assumption: true`, and the loader rejects bare numbers. Calibrated values say which validation case they were fit on.
- `application/simulate.py`: `POST /api/v1/simulate`. `application/simulation_service.py` is the facade the routes use.
- `GET /api/v1/sim/network`: areas and corridors with the real node and line ids they aggregate. A substation id from the map (`SE…`) is a valid target everywhere.
- Validation cases: `tests/validation/test_engine_cases.py` runs V1-V5, V7, V8 and V10 on the real snapshot. V6 and V9 are skipped until their reference data is in the repo.
