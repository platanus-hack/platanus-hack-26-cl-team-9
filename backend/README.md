# Sub50 backend: unified grid data API

The Python package and commands keep the earlier working name, `cascadasen`.

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
- `GET /api/v1/sim/network?point=`: the mapa 3 network (`B###`, `R###`) with the theatre's areas, corridors and defences. Any area, corridor, `B###`, `R###` or `SE…` id is a valid user target. The strategic theatre runs on this network and the mapa 3 cascade engine (`domain/theater/{areas,grid}.py`).
- Validation cases: `tests/validation/test_engine_cases.py` runs V1-V5, V7, V8 and V10 on the real snapshot. V6 and V9 are skipped until their reference data is in the repo.
- `domain/theater/`: strategic layer (`docs/strategy.md`).
  - State and supervision: real vs observed state (`state.py`), and the digital engine for missing, stale or unreliable supervision and false alarms (`digital.py`).
  - Catalog: abstract events and defensive actions (`catalog.py`).
  - Control: resource ledger (`resources.py`), deterministic validator (`validator.py`), and the execution engine with effect lifecycles and restoration (`execution.py`).
  - Record and orchestration: hash-chained audit log (`audit.py`), indicators and the Freedom of Action Index (`evaluator.py`), and the six-step cycle (`cycle.py`).
  - Experiment design lives in `params/theater.yaml` and `params/templates.yaml`.
- `domain/agents/`: C2, ISR, Operations, Stabilisation, Logistics, Auditor and the adaptive Adversary. They are deterministic and seeded. Views (`base.py`) never carry the real state, which a test checks.
- `application/run_experiment.py`: `RunManager` (in-memory LRU of 100 runs; replay re-injects events at their cycles, so an unchanged replay gives the same trace hash) and the catalog. Endpoints are under `/api/v1/sim/*` (`docs/stack.md` 7.1).
- `domain/theater/narrative.py` and `params/narrative_es.yaml`: Spanish templates for every key the API returns, plus the deterministic after-action review (`TemplateInterpreter`, behind the `Interpreter` port in `domain/ports.py`). An LLM-backed interpreter can implement the same port later; it would explain, never decide.
- Optional LLM (off by default): `uv sync --extra llm`, then in `backend/.env` (git-ignored; settings only, **never keys**):
  - Amazon Bedrock with an AWS profile (credentials stay in `~/.aws`, e.g. `aws configure --profile cascadasen` or `aws sso login --profile cascadasen`):
    ```
    CASCADASEN_LLM_ENABLED=true
    CASCADASEN_LLM_PROVIDER=bedrock
    CASCADASEN_AWS_REGION=us-east-1
    CASCADASEN_AWS_PROFILE=cascadasen
    ```
    The model id gets the Bedrock prefix (`anthropic.claude-opus-5-5`); Bedrock has no server-side refusal fallback, so a refusal falls back to the rules.
  - Claude API: `CASCADASEN_LLM_ENABLED=true` and `ANTHROPIC_API_KEY` in your shell (or an `ant auth login` profile).

  Runs created with `"llm_commander": true` let the LLM pick C2's actions among validated ones; `after_action` adds a narrative. Settings: `CASCADASEN_LLM_MODEL` (default `claude-opus-5-5`), `CASCADASEN_LLM_EFFORT` (default `low`), `CASCADASEN_LLM_TIMEOUT_S`. Every failure (no profile, no model access, timeout, refusal) falls back to the deterministic path and is logged as `llm_unavailable` in the audit.
- `uv run cascadasen-sim-fixtures [--point ID] [--seed N] [--no-campaign] [--out DIR]` writes the offline theatre cache for mapa 3 to `web/public/cache/theater/` (git-ignored): `index.json`, networks, one flagship run per policy and point, and a campaign per point. The files are generated: regenerate them, do not edit them.

### Validation cases (`docs/plan.md` section 5)

| Case | What | Target | Status |
|---|---|---|---|
| V1 | 25F flow split on A06-A07 | 1,800 / 314 MW within 15 % | passes (220 kV reactance calibrated on it) |
| V2 | Opening the 25F corridor forms the two islands | A01-A06 and A07-A13 | passes |
| V3a | 25F with the north defence scheme at 0.23 s, per code | maintains; min 48.5 ± 0.3 Hz; shed 1,467.8 MW ± 20 % | passes (48.53 Hz, 1,681 MW) |
| V3b | No defence scheme, per code | maintains; shed 2,040.7 MW ± 20 % | passes (1,674 MW) |
| V4 | 25F as it happened | blackout; 47.5 Hz at 4.6 ± 1 s | passes (3.95 s) |
| V5 | North after separation | ~51.3 ± 0.3 Hz | passes (51.23 Hz) |
| V6 | Seven north 500 kV segments | CEN classification | skipped: reference table not in the repo |
| V7 | Low demand 2026, loss of 3,000 MW | maintains; ≥ 48.1 Hz; ~-2 Hz/s | passes (48.38 Hz, -2.08 Hz/s) |
| V8 | As V7 with step 3 inactive | blackout | passes |
| V9 | Polpaico frequency curve | RMSE 0-5 s | skipped: digitised curve not in the repo |
| V10 | 103 MW lost in Norte Grande at midday | L0 or L1 | passes (L0) |
