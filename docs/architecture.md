# Architecture

How Sub50 is built today (2026-11-21): the pieces, how they depend on each other, and where each responsibility lives. Product and scope are in `idea.md`, the simulation model in `stack.md` section 4, data contracts and API in `stack.md` sections 6-7. When code and this document disagree, the code wins; fix this document in the same change.

## 1. System overview

```
 public sources (CEN Infotécnica, IDE Energía, INE, PyPSA-CL)
          │  cascadasen-build (source adapters, unify, validation)
          ▼
 data/processed/  grid_snapshot.json, operating_points.json, baseline_opf.json, geo/*.geojson
          │                                   │
          │ cascadasen-cache                  │ cascadasen-api (FastAPI)
          │ cascadasen-sim-fixtures           │   /api/v1/*          grid queries
          ▼                                   │   /api/v1/simulate   13-area engine
 web/public/cache/  precomputed cuts          │   /api/v1/sim/*      strategic theatre
          │  and offline theatre runs         │
          ▼                                   ▼
 web/ (Vite + React + deck.gl / Mapbox): mapa 3 reads the static cache, and the live API when a server is up
```

Principles (`stack.md` section 2):

- Physics lives only in the backend. The frontend draws what the engine returns and never computes physics.
- The demo works without a server: every line cut is precomputed into `web/public/cache/`.
- Every parameter carries a source or `is_assumption: true` (`datasets.md` section 6). The YAML loaders reject bare numbers.
- Runs are deterministic: one seed per run, independent seeded streams, no wall clock in the domain.

## 2. Backend: ports and adapters (hexagonal)

Python package `cascadasen` in `backend/src/cascadasen/`, managed with `uv`.

```
api/  (FastAPI routes: driving adapter)
  │
  ▼
application/  (use cases: build, query, simulate, runs, campaigns, cache)
  │
  ▼
domain/  (model, physics, theatre, agents, ports)  ◄──  infrastructure/  (adapters, settings, composition root)
```

Dependency rule: `domain/` imports nothing from `api/`, `application/` or `infrastructure/`. Adapters implement the ports of `domain/ports.py`; `infrastructure/container.py` wires them (composition root).

### 2.1 Ports (`domain/ports.py`)

| Port | What it abstracts | Adapters |
|---|---|---|
| `GridDataSource` | One public data source contributing to a `SourceBundle` | `infrastructure/sources/{infotecnica,ide_energia,ine_censo,pypsa_cl}.py` |
| `SnapshotRepository` | Where the unified snapshot is stored and read | `infrastructure/snapshot_repository.py` (JSON) |
| `ContractExporter` | Static files for the frontend | `infrastructure/exporters.py` |
| `Interpreter` | Narration and after-action review | `domain/theater/narrative.py` (`TemplateInterpreter`), `infrastructure/llm.py` (`ClaudeInterpreter`) |
| `CommanderAdvisor` | An LLM that picks among validated COAs for C2 | `infrastructure/llm.py` (Claude API, Bedrock, Bedrock Converse) |
| `DocumentStore` | JSON documents by key with conditional writes (`if_match`, `if_none_match`; a lost race raises `ConflictError`) for run records and sessions | `infrastructure/document_store.py` (memory, file, S3) |

Adding a data source means writing one adapter and registering it in `container.py`; domain and application do not change.

### 2.2 Domain (`domain/`)

| Module | Responsibility |
|---|---|
| `model.py`, `unify.py`, `topology_inference.py`, `naming.py`, `geo.py` | Grid model; joins the sources into one snapshot (substations by CEN id, line ends from geometry, PyPSA-CL parameters, population) as pure functions |
| `validation.py` | Checks run on every build (coverage, connectivity, agreement between sources, reactance per km) |
| `cascade/` | **188-bus cascade engine** (`engine.md`): network reduction, DC flow per island, island frequency (reserve with droop, batteries, EDAC, extreme EDAC), overload cascade, voltage-limited verdict. Parameters in `cascade/params/cascade.yaml`. Drives the map cuts and the theatre |
| `cascade/overlay.py` | **Session overlay** (`stack.md` 6.2): validated edits of the 188-bus network and per-bus arrays (added buses, lines, loads and datacenters, generators, overrides, out-of-service), rebalanced per island by proportional synchronous redispatch (an assumption). Pure, no wall clock |
| `simulation/` | **13-area engine** for `POST /api/v1/simulate` and validation cases V1-V10. Parameters in `simulation/params/*.yaml`; its `params.py` loader is shared by the other modules |
| `theater/` | **Strategic theatre** (`strategy.md`): real state on the mapa 3 network (`grid.py`), digital engine (`digital.py`), events and actions (`catalog.py`, `execution.py`), validator, resources, crews, chance (`rng.py`, `stochastic.py`), evaluator, hash-chained audit log, the cycle (`cycle.py`). Parameters in `theater/params/*.yaml` |
| `agents/` | C2, ISR, Operations, Stabilisation, Logistics, Auditor and the adaptive adversary (`strategy.md` section 5, `agents.md`). They receive views (`base.py`) and never the real state |

Two engines exist on purpose: the 13-area engine holds the 25F validation cases; the 188-bus engine draws on the real map and runs the theatre (`plan.md` section 9.4).

### 2.3 Application (`application/`)

| Use case | File | Exposed as |
|---|---|---|
| Build the unified snapshot | `build_grid.py` | `cascadasen-build` (`cli.py`) |
| Query the grid | `grid_queries.py` | `/api/v1/nodes`, `/edges`, `/graph/*`, ... |
| Simulate a scenario (13 areas) | `simulate.py` | `POST /api/v1/simulate` |
| Theatre world (network + operating points, cached); `SessionWorld` = one pinned point with a session overlay applied | `theater_world.py` | used by runs, campaigns and session runs |
| Sessions: document CRUD with revisions and conditional writes, overlay edits, network view with baseline, sandbox cut/repair, nested runs on `RunManager` pinned to their overlay, revision/head for SSE | `sessions.py` | `/api/v1/sessions*` (API in a later change) |
| Runs: create, step, inject, external actions, replay; every command persists a run record in the `DocumentStore`, a bounded `RunCache` (LRU) keeps live simulations and rebuilds evicted ones | `run_experiment.py` | `/api/v1/sim/runs*` |
| Campaigns with fragility and adaptation indices | `run_campaign.py` | `/api/v1/sim/campaigns*` |
| Facade over simulation and theatre | `simulation_service.py` | `api/simulation_routes.py` |
| Precompute every single-line cut | `cache_builder.py` | `cascadasen-cache` → `web/public/cache/` |
| Precompute offline theatre runs | `sim_fixtures.py` | `cascadasen-sim-fixtures` → `web/public/cache/theater/` |

### 2.4 Infrastructure (`infrastructure/`)

- `sources/*`: one adapter per public source. Downloads are cached in `data/raw/`, which is git-ignored.
- `http.py`, `arcgis.py`: cached HTTP client and ArcGIS paging.
- `snapshot_repository.py`, `exporters.py`: persistence and static files.
- `llm.py`: Claude API and Amazon Bedrock clients. Optional extra `llm`, off by default (`CASCADASEN_LLM_ENABLED`).
- `document_store.py`: `MemoryDocumentStore` (default), `FileDocumentStore` (`data/sessions/`, git-ignored; atomic writes, rejects keys with `..`) and `S3DocumentStore` (S3 conditional writes `IfMatch`/`IfNoneMatch`). Chosen by `CASCADASEN_SESSION_STORE` (`memory`, `file`, `s3` with `CASCADASEN_SESSION_BUCKET`) in `container.document_store`. Memory and file entries expire `CASCADASEN_SESSION_TTL_HOURS` (24) after their last write; S3 relies on a bucket lifecycle rule.
- `settings.py`: settings `CASCADASEN_*` from the environment or `backend/.env`. Keys are never stored there.
- `container.py`: composition root.

### 2.5 API (`api/`)

`app.py` creates the FastAPI app (grid queries, health, admin reload when `CASCADASEN_ADMIN_ENABLED=true`, the `static/map.html` test page) and sets `app.state.settings` and `app.state.store` and includes `simulation_routes.py` (`/api/v1/simulate`, `/api/v1/sim/*`) and `session_routes.py` (`/api/v1/sessions/*`, built lazily on `app.state.sessions` from the simulation service). `limits.py` holds the per-process rate limits (`TokenBucket`), SSE slots and the 64 KB `BodyLimitMiddleware` for session routes. Schemas are in `schemas.py` (with the shared `ErrorResponse`), `simulation_schemas.py` and `session_schemas.py`. HTTP contract: `stack.md` sections 7, 7.1 and 7.2, and `sessions-api.md`. Command: `cascadasen-api`.

## 3. Simulation flows

### 3.1 A line cut (map, `engine.md`)

```
cut ─► islands ─► frequency per island (20 s, 10 ms step) ─► DC flow ─► line > 120 %? ─► open it ─► repeat (≤ 20 stages)
                   reserve, batteries, EDAC, blackout < 47.5 Hz
```

The result is a timeline: events, one frame per stage, 5 Hz frequency curves, and a summary with islands, load shed, people without power and `uncertain`. The map reads it precomputed from `web/public/cache/`.

### 3.2 One theatre cycle (`strategy.md` section 7)

```
tick (expire effects, restore, settle frequency)
  ─► events (scenario, user, adversary, unplanned) ─► cascade engine on the current state
  ─► digital engine: real state ─► observed state per role (missing, stale, unreliable, false alarms)
  ─► ISR ─► C2 intent ─► Operations / Stabilisation / Logistics propose COAs
  ─► validator (on the real state) + vetoes ─► C2 decides (rules, optional LLM pick)
  ─► execute ─► evaluator + auditor ─► adversary learns
```

There are three states (`strategy.md` section 3). The real state is seen only by the engine, the validator and the evaluator. Agents see the observed state through their role. Each agent keeps its own estimate. A run can be replayed exactly from its recipe: configuration, seed, injected events and recorded LLM picks.

### 3.3 A session edit and its live update (`sessions-api.md`)

```
client A: POST /sessions/{sid}/loads ─► SessionService.mutate: get doc ─► overlay.add + apply_overlay (validate, rebalance)
          ─► revision+1, last_op ─► store.put(if_match=etag) (conflict: re-read, ≤ 3 retries, then 409) ─► 201 + ETag
client B: GET /sessions/{sid}/events (SSE) ─► every 1 s: cached revision; every 5 s: store head (another instance wrote?)
          ─► event: revision {revision, op, ids, by} ─► B refetches /network and /state
```

The network view is cached per `(sid, revision)`. Runs created in the session pin the overlay of that moment in their record, so later edits do not change them.

## 4. Frontend (`web/`)

Vite + React + TypeScript; deck.gl layers over an offline base map or Mapbox (token as build arg).

| Folder | Responsibility |
|---|---|
| `src/cascade/` | Mapa 3 (`CascadeApp.tsx`): Red, Simulación, Leyenda and Supuestos tabs; line cut, cascade layers, network panel, timeline player. Data from `web/public/cache/` (`api.ts`) |
| `src/map/` | Base map (offline or Mapbox), shared layers, node detail |
| `src/assets/icons/` | 2D icons |

The operation tab, which draws the theatre on mapa 3, is not on `feat/strategic-sim-api`, a backend-only PR. It returns in a frontend PR (`agents.md` section 4). Visual rules: `design.md`.

## 5. Data and parameters

- `data/scripts/`: `build_operating_points.py` (demand per bus), `build_baseline_opf.py` (secure base case: DC OPF, inertia floor), `build_node_index.py`, `build_chile_outline.sh`.
- `data/processed/`: snapshot, operating points, base case and geo layers. It is versioned so the demo does not depend on downloads.
- Parameters: `domain/cascade/params/cascade.yaml`, `domain/simulation/params/*.yaml`, `domain/theater/params/*.yaml`. Provenance is enforced at load time. One known impurity: these loaders read files from the domain package, accepted because the files ship with the code.

## 6. Deployment and tooling

- Local: `docker compose` (backend + Vite dev server, `docker.md`).
- AWS: ECS Fargate behind ALB and CloudFront, with production images and Terraform in `infrastructure/` (`infrastructure.md`).
- Quality:
  - `scripts/lint.sh` (ruff for Python);
  - git hook `scripts/hooks/pre-commit` (lint + `CHANGELOG.md`);
  - CI `.github/workflows/lint.yml` (ruff + changelog);
  - tests: `cd backend && uv run pytest` and `cd web && npx vitest run`.
- Agent workflow: `AGENTS.md`, plus the `CHANGELOG.md` written for agents.
