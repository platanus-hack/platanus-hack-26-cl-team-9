# Stack and architecture

Status: revised after the planning session of 2026-11-21 and updated the same day to match the repo. Implemented so far: the grid data pipeline and read-only API (`backend/`, `datasets.md` section 0), the web map (`web/`, deck.gl offline map plus an optional Mapbox basemap), operating points and a secure DC-OPF base case (`data/scripts/`), Docker Compose and lint CI. Not implemented: the cascade engine, the timeline player and the fixtures in section 6. Visual direction: `design.md`.

## 0. MVP scope

The first MVPs are frontend only. The browser app reads a hand-written `network.json` and `timeline.json` fixture (the data contract in section 6). The app contains no physics and no server.

Backend work (simulation engine, API, cache builder, CI) is backlog. Each backlog item gets a GitHub issue. The first MVPs do not depend on any backend item.

Consequences for the first MVPs:
- Every result on screen comes from fixtures, not from a computed simulation. Fixture numbers are placeholders and must carry an "assumption" or "fixture" label. The validation table stays empty or marked "not computed" until the engine exists.
- When the engine arrives, it writes files in the same format as the fixtures. The frontend code should not change.
- Frontend tests cover the logic the app owns: the playback clock, narration templates, layer mapping and fixture validation against the JSON schema.

## 1. Decisions

Status column: **MVP** means needed for the first frontend MVPs. **Backlog** means tracked as a GitHub issue and not started.

| Layer | Choice | Status | Notes |
|---|---|---|---|
| Frontend | React + Vite + TypeScript | MVP | Decided earlier |
| Map and 3D-style layers | deck.gl; Mapbox basemap when `VITE_MAPBOX_TOKEN` is set, offline Chile outline otherwise (`createBaseMap`) | Done | The main map (`/`, also `?mapa=3`) is mapa 3, the cascade viewer (`docs/mapa3.md`), with a 2D / 3D toggle (`?vista=2d`) and city labels. `?mapa=1` (offline deck.gl map) and `?mapa=2` (Mapbox) are deprecated and kept as reference. The strategic theatre's operation mode is specified for this map (`mapa3.md` section 10) |
| Chile outline | Local simplified GeoJSON (Natural Earth admin-1 or IDE Chile/BCN, simplified with mapshaper) | MVP | Continental Chile only; see `datasets.md` |
| State | Zustand | MVP | Holds one playback clock `t` that drives all animations |
| Charts | uPlot | MVP | Frequency curve synchronised with `t`, read from fixture data |
| Simulation engine | Python 3.11, numpy, networkx | Backlog (base case started) | Started: `data/scripts/build_operating_points.py` (PyPSA-CL demand and merit-order dispatch for 4 hours) and `build_baseline_opf.py` (DC-OPF so no branch exceeds s_nom, with an inertia floor; N-1 not enforced). No cascade or frequency model yet. Plan: one-equation-per-island frequency model; DC power flow solved with numpy. pandapower only if the full official network arrives (Plan A, optional). The MVP uses fixtures instead |
| API | FastAPI (REST; WebSocket optional for live combinations) | Backlog | Needed only for combinations not in the cache |
| Precompute | Script that runs every single-element failure for every scenario x defences x behaviour and writes static JSON | Backlog | MVP ships hand-written files in `web/public/cache/` in the same format |
| Tests | Vitest (frontend logic) | MVP | pytest (engine, validation, provenance) is backlog |
| CI | GitHub Actions | Lint: done. Rest: backlog | `.github/workflows/lint.yml` runs ruff and requires a `CHANGELOG.md` change in each pull request. Generating the validation table from the tests is still backlog |
| Lint and agent tooling | ruff (Python), eslint/prettier (frontend, once installed), git and Claude Code hooks | Done | Single entry point `scripts/lint.sh`; rules and hooks in `AGENTS.md` |
| Local run | Docker Compose (`web` Vite dev server, `backend` data API) | MVP | `docker compose up --build`, only Docker needed. See `docs/docker.md` |
| Hosting | Static frontend plus fixtures; deploy from a personal mirror (see README of the template) | MVP | Platforms like Vercel cannot access the org repo |
| LLM | Not in the core | Backlog (P2) | Narration uses fixed templates so every sentence is reproducible. An optional chat that calls the simulator is P2 |

## 2. Architecture

```
datasets (public APIs) --scripts--> data/processed/network.json
                                         |
                                         v
        engine (Python) --simulate()--> timeline.json (events + frames + summary + provenance)
              |                                  |
              | build_cache.py                   | POST /simulate (combinations only)
              v                                  v
        web/public/cache/*.json  ------>  frontend player (reads timeline, renders from clock t)
```

The diagram is the original target. The architecture as built (backend ports and adapters, the two engines, the strategic theatre, frontend and deployment) is in [`architecture.md`](architecture.md). In particular, `network.json` does not exist: the engines read `data/processed/{grid_snapshot,operating_points,baseline_opf}.json`, and the cache lives in `web/public/cache/`.

Principles:
- The engine is the only place with physics. The frontend never computes physics, so there are no two implementations to diverge.
- The frontend is a pure function of (`network.json`, `timeline.json`, clock `t`). Play, pause, scrub and speed come for free.
- The contract (section 6) is frozen in hour 0 so frontend and engine can be built in parallel. The frontend develops against a hand-written fake timeline until the engine is ready.
- Every parameter has a source or an explicit `assumption` flag. A test fails if one has neither.

## 3. Repository layout

Current layout (2026-11-21). Entries marked (backlog) do not exist yet.

```
AGENTS.md, CLAUDE.md  agent workflow rules; CHANGELOG.md is written for agents
docs/                 this documentation
backend/              Python package `cascadasen` (uv), ports and adapters (`architecture.md`): source adapters, unify,
                      validation, the two engines (`domain/cascade`, `domain/simulation`), the strategic theatre and
                      its agents, FastAPI, tests
data/
  scripts/            build_chile_outline.sh, build_node_index.py, build_operating_points.py, build_baseline_opf.py
  raw/                downloaded sources (git-ignored cache)
  processed/          grid_snapshot.json, sen_network.json, geo/*.geojson, chile.geojson, node_index.json,
                      operating_points.json, baseline_opf.json, atlas_sen.html
web/                  Vite + React + TypeScript app (deck.gl map, Mapbox option, node popup)
  public/cache/       precomputed cuts per operating point (`cascadasen-cache`) and offline theatre runs
infrastructure/       Terraform and deploy script for AWS (`infrastructure.md`)
scripts/              lint.sh and git hooks
docker-compose.yml    backend and web services (`docs/docker.md`)
.github/workflows/    lint.yml (ruff and changelog check)
```

## 4. Simulation model

Seed values below come from the team's earlier research of the CEN reports. The ones marked (verified) were re-checked against the reports by the independent evaluator; the rest were not independently re-checked and the engineer should confirm them in the cited source before relying on them. [n] refers to `datasets.md` section 7.

### 4.1 Network
Graph of about 10-14 nodes along the north-south trunk (Norte Grande, Atacama, Coquimbo, Valparaiso, Metropolitana, centre, Biobio, south, plus 2-3 southern nodes). Each corridor between nodes aggregates its 500 kV and 220 kV lines with an equivalent reactance and capacity. Parallel lines at different voltages stay as separate edges because that is how the 25F cascade happened [4]. Each node has generation and demand for the chosen scenario.

### 4.2 Power flow
DC power flow (flow proportional to angle difference over reactance), solved per island with numpy.

### 4.3 Cascade rules
1. Open the failed elements chosen by the user.
2. Detect islands (connected components, networkx).
3. Compute each island's initial imbalance: generation minus load, plus the flow that crossed the boundary.
4. Run the island frequency model (4.4). An island that collapses loses all its load.
5. DC flow on surviving islands. Per iteration open only the corridor with the highest relative loading above 120% of capacity (parameter); ties open together.
6. Distribute remaining imbalance among synchronous generators in proportion to available reserve.
7. Automatic under-frequency load shedding (EDAC) applies per zone with the amounts of each zone, proportional across buses with positive load. Exclude buses with net negative load (distributed generation larger than demand).
8. Overloads in the first ~2 s are labelled "separation through a weak link" (the 25F mechanism [4]). Later overloads are labelled "thermal overload, needs operator action" and do not trip anything in the default mode.
9. Cap at 20 iterations; if reached, return `truncated: true`.

### 4.4 Island frequency model
Aggregated swing equation, 10 ms step, 20 s horizon:

```
(2*E_i / f0) * df/dt = P_gen(t) + P_reserve(t) + P_bat(t) - P_load(t) - dP_load(f)
dP_load(f) = (D_pct_per_Hz / 100) * P_load * (f - f0),   D_pct_per_Hz in [1, 2]  (assumption)
```

Seed values (25F, centre-south):
- Kinetic energy E: 11.72 and 22.46 GVAs for the two islands [4] Table 4-1. When a synchronous unit trips, subtract its inertia (without this the model gives 1.69 Hz/s for a 3,000 MW loss with 44.3 GVAs, while the CEN reports about 2 Hz/s [14]).
- Initial imbalance: 2,114 MW (net flow lost across the boundary [4]).
- Link between the two areas before separation: P_link = 314 MW for t < t_sep, 0 after. t_sep = 1.566 s as it happened, 0.23 s with the north defence scheme [4].
- Primary reserve: first-order, capped at the published reserve (267.99 + 22.07 MW in the centre-south on 25F [4] Table 4-1). Time constant and D are calibrated only on case V3a.
- EDAC by low frequency: steps from [4] Table 3-10 (25F) or [14] Table 1 and the Annex E spreadsheet [16] (2026), each with threshold and effectiveness factor.
- EDAC for extreme contingency: 671.55 MW in the centre-south, threshold 49.5 Hz, gradients -0.9 / -1.2 / -1.9 Hz/s [4] Table 3-11.
- Blackout threshold: 47.5 Hz (NTSyCS art. 3-10, per [4]).
- Island with surplus: automatic generation shedding and renewable curtailment (in case 1 of [4] the control reduced 1,922.3 MW).
- Mode "as it happened": the 25F events with their times. Use the corrected generation figures: about 1,971 MW of generation disconnected in the centre-south, and 737.34 MW of unidentified disconnected generation had to be added to the CEN model to match measured frequency (verified [4]). The older "about 1,000 MW" figure in earlier drafts is superseded; do not use it.

### 4.5 Batteries and "what would have prevented it"
- `P_bat(t) = min(P_max, P_max * (t - t_d) / t_r)` for `t > t_d`. Defaults t_d = 200 ms, t_r = 300 ms; sensitivity with t_d = 500 ms [18].
- Size batteries per island, not per location (the model has no position inside an island).
- Existing storage counts as generation without frequency response (conservative assumption).
- Output a curve "MW needed vs t_d", found by binary search on P_max.
- Minimal combinations: enumerate the 25F failure events (2^5 = 32 cases) and report the minimal set that changes the outcome.
- Islands with no synchronous generation and under 200 MW (parameter) are reported as "local cut", not as cascade blackout.

### 4.6 Island result categories

| Result | Meaning |
|---|---|
| Maintains | Frequency model says the island balances |
| Blackout | Frequency falls below the trip limit |
| Uncertain: outside what the model evaluates | Pre-failure flow on the lost north 500 kV corridor exceeds the validity range of the CEN north defence scheme (1,600 MW north-to-south, 1,000 MW south-to-north [4]; 1,700 MW per [6]); voltage may dominate there |
| Not modelled | The case needs something the model lacks (e.g. an island without defence data) |

In the 188-bus cascade engine (`engine.md`) the uncertain verdict is `result: "voltage_limited"` with `summary.uncertain: true`, raised when a cut opens the 25F boundary with a pre-fault flow outside that range. The UI label is "limitado por tensión (incierto), evento documentado, no calculado".

Consequence levels L0-L3 (`cyber.md` section 5) aggregate these island results into one headline value per run.

The 25F replica is the declared exception: it reports the frequency result because a published reference exists. An optional overvoltage flag (low-demand scenario, load shed above ~2,300 MW) adds "overvoltage risk (not modelled)".

## 5. Frontend design

The look, layout, colors and zoom behaviour are defined in `design.md` (Electricity Maps style, decided on 2026-11-21). Where this section disagrees with `design.md` on visuals, `design.md` wins. This section keeps the layer and animation mechanics.

### 5.1 Layout
Variant A in `design.md` section 2: a quiet floating panel on the left (headline counter, event chain, validation, selectors in tabs) and the map on the right, with a timeline card (play, scrub, frequency curve) and a legend card. The camera follows the cascade north to south and uses fly-to transitions.

### 5.2 deck.gl layers and animations

| Element | Layer | Animation |
|---|---|---|
| Chile outline | `GeoJsonLayer` | None; dark night style |
| Generators | `ColumnLayer` (height = MW, colour = technology) | Column drops to zero when the plant trips |
| Cities | `ScatterplotLayer`, cream, no glow at country zoom (`design.md` section 4) | Wave of darkness: each city goes out according to time since its island collapsed |
| Transmission lines | `PathLayer`, colour by voltage with lightness falling with voltage (`design.md` section 3); only 220 kV and above at country zoom | Red and pulsing when overloaded; dashed gray when open |
| Power flow | `TripsLayer` | Particles move along lines; they reroute when a line is cut |
| Cut | `ScatterplotLayer` | Expanding ring and flash at the cut |
| Substations / nodes | `ScatterplotLayer` + `TextLayer` | Colour by island |
| Camera | `viewState` transitions | Fly to the failure, then to the two islands |

Render the 1,193 plants aggregated per node (one column per node with summed MW) and reveal individual plants on zoom. 1,193 loose columns look like noise. Icons appear by zoom level in order of real size and importance (`design.md` section 4).

The simulation's electrical time (0-20 s) and the visible story time differ. The animation maps electrical events to a ~5 s playback with a speed control. Documented events outside the 20 s horizon (the north's voltage collapse about 4 minutes later) are shown as annotated events labelled "documented".

### 5.3 Transparency UI
Hover on any number shows document and page, or the badge "assumption" / "approximate". Show on screen which network was used ("reduced network, public data").

## 6. Data contracts (draft; freeze in hour 0)

`data/processed/network.json`:
```json
{
  "version": 1,
  "nodes": [{"id": "N05", "name": "Nueva Pan de Azucar", "lon": -71.0, "lat": -30.0,
             "population": 0, "demand_mw": {"25F": 0}, "generation_mw": {"25F": 0},
             "source": "...", "is_assumption": false}],
  "edges": [{"id": "E05", "from": "N04", "to": "N05", "kv": 500, "circuits": 2,
             "capacity_mw": 0, "reactance": 0, "source": "...", "is_assumption": true}],
  "plants": [{"id": "P001", "name": "...", "tech": "solar", "mw": 0.0, "lon": 0, "lat": 0,
              "node": "N05", "source": "IDE Energia capa solares"}],
  "cities": [{"id": "C01", "name": "Santiago", "lon": 0, "lat": 0, "population": 0, "node": "N08"}]
}
```
Values above are placeholders; the node list and ids are decided in phase 0.

`timeline.json` (one per scenario x defences x behaviour x failed elements):
```json
{
  "scenario": "25F", "defenses": "25F", "behavior": "as_happened", "failed_elements": ["E05"],
  "duration_s": 20, "truncated": false,
  "events": [{"t": 0.0, "type": "line_cut", "ids": ["E05"], "text_key": "line_cut", "params": {}}],
  "frames": [{"t": 0.0,
              "edges": {"E05": {"flow_mw": 1800, "status": "ok"}},
              "nodes": {"N05": {"energized": true, "island": "I1"}},
              "islands": {"I1": {"freq_hz": 50.0}}}],
  "summary": {"people_without_power": 0, "load_shed_mw": 0,
              "islands": [{"id": "I1", "result": "blackout", "nodes": ["N05"]}]},
  "provenance": [{"key": "inertia_I1", "source": "[4] Table 4-1", "is_assumption": false}]
}
```
Event types: `line_cut`, `line_overload_open`, `island_formed`, `plant_trip`, `load_shed`, `island_blackout`, `island_stable`, `documented_event`. Edge `status`: `ok`, `overload`, `open`. Frames sampled at about 10 Hz plus the events. Narration is generated in the UI from `text_key` + `params` using Spanish templates.

### 6.1 Optional fields for cyber consequence scenarios (draft)

These fields support the scenario classes in `cyber.md` section 4. All are optional, so files without them, including the MVP fixtures, stay valid.

```json
{
  "cause": {"kind": "cyber_effect", "scenario_class": "C6", "label_key": "cyber_hypothetical",
            "references": ["[34]"]},
  "group_out": [{"zone": "norte_grande", "tech": "solar", "share": 0.4}],
  "defenses_disabled": ["pdce_zn"],
  "summary": {"consequence_level": "L2",
              "unserved_energy_mwh": 0, "failure_cost_usd": 0,
              "outage_duration_h": {"value": 0, "is_assumption": true}}
}
```

- `cause.kind`: `failure` (default) or `cyber_effect`. When it is `cyber_effect`, the UI shows the notice "Escenario hipotético: se modela el efecto, no el ataque."
- `group_out` is defined by zone and technology only, never by plant or company (`cyber.md` section 8).
- New event types: `defense_disabled` (a defence that does not act) and `control_lost` (plants that stay online but give no dispatch or reserve).
- `consequence_level`: `L0` absorbed, `L1` contained, `L2` regional blackout, `L3` national blackout.
- `failure_cost_usd` = `unserved_energy_mwh` x 1,000 x 8.79 US$/kWh [19]. The value is a regulatory valuation and depends on the assumed duration.

### 6.2 Session overlay
A session edits the 188-bus engine network (`domain/cascade/network.py`) of one pinned operating point through a JSON overlay (`domain/cascade/overlay.py`). The base dataset is never changed. The session document `sessions/<sid>.json` (`application/sessions.py`) is:
```json
{
  "session_id": "<22 chars, secrets.token_urlsafe(16)>", "label": null, "point": "nov2026-1300",
  "revision": 3, "dataset_revision": 2, "open_lines": ["R014"],
  "overlay": {
    "buses": [{"id": "B188", "name": "Nueva SE", "lat": -33.5, "lon": -70.7, "kv": 220}],
    "lines": [{"id": "U001", "a": "B010", "b": "B188", "kv": 220, "capacity_mw": 500, "x_pu": 0.0123}],
    "loads": [{"id": "D001", "bus": "B010", "mw": 300, "kind": "datacenter", "name": "DC"}],
    "generators": [{"id": "G001", "bus": "B188", "mw": 100, "tech": "solar"}],
    "bus_overrides": {"B002": {"load_mw": 120, "in_service": true}},
    "line_overrides": {"R001": {"capacity_mw": 800, "in_service": false}},
    "seq": {"line": 1, "load": 1, "generator": 1}
  },
  "runs": {"<run_id>": {"created_at": "...", "dataset_revision": 1, "cycle": 5, "status": "running"}},
  "created_at": "...", "updated_at": "...",
  "last_op": {"op": "load_added", "ids": ["D001"], "by": "web", "revision": 3, "dataset_revision": 2}
}
```
- **Ids.** Added buses continue the base numbering (`B188`, `B189`… on the real network). Added lines are `U###`, loads and datacenters `D###`, generators `G###`; the `seq` counters never reuse an id. Element references use these ids (`a`, `b`, `bus`).
- **Edits.** `add`, `patch` and `remove` per kind (`bus`, `line`, `load`, `generator`). A patch on a base bus or line writes `bus_overrides`/`line_overrides` (bus: `name`, `kv`, `lat`, `lon`, `load_mw`, `gen_mw`, `sync_mw`, `inertia_mws`, `in_service`; line: `capacity_mw`, `x_pu`, `in_service`); a `null` clears a field. Base elements are never deleted (409, use `in_service: false`). An out-of-service bus keeps its index with load, generation, synchronous MW and inertia at 0, and its lines are dropped. Deleting a session bus leaves a tombstone (`removed: true`, hidden from views) so later ids stay stable; it is refused (409) while lines, loads or generators reference it.
- **Bounds.** `kv` in the base set (66, 110, 154, 220, 500); line ends distinct, existing and in service; `capacity_mw` in (0, 5000]; `x_pu` in [5e-4, 1.0], default `haversine_km × mean(X_PER_KM[kv]) / (kv²/100)` (`domain/validation.py`); load and generator `mw` in (0, 3000]; bus overrides `load_mw`, `gen_mw`, `sync_mw` in [0, base value + 3000] with `sync_mw ≤ gen_mw` and `inertia_mws ≤ 10 s × sync_mw`; lat in [-56, -17], lon in [-76, -66]; at most 50 added elements and 5000 MW of added load plus generation plus the absolute `load_mw` and `gen_mw` change of bus overrides. Generator `tech` is `hidro`, `termica`, `bioenergia`, `geotermica` (synchronous by default, inertia `inertia_h × mw`, `inertia_h` default 4 s, an assumption) or `solar`, `eolica`; load `kind` is `datacenter` or `consumo`.
- **Balance rule (`is_assumption: true`).** Per island of the edited network, `delta = Σ(gen'−load') − Σ(gen−load)` (edited versus base arrays) is redispatched as `−delta` over the base synchronous units of the island in proportion to their base `sync_mw`; `gen` and `sync_mw` change, inertia does not; a unit is clamped at 0. A bus whose `gen_mw` or `sync_mw` the overlay sets keeps that value and takes no share. A bus out of service loses its base load and generation; when it (or a group of adjacent out-of-service buses) touched a single live island through its in-service base lines, that island redispatches the loss, so the base case stays balanced. When it touched several islands it split them, and each part keeps its base imbalance (`unbalanced_island`). Out-of-service buses get no warnings of their own. Each redispatch is reported as `balance: [{buses: {"B000": 54.5, …}, redispatch_mw, is_assumption: true, rule}]`. It is not an OPF: a large added load can overload lines in the base case, and the baseline shows it.
- **Warnings** `{code, ids, message}`: `isolated_bus` (a bus with no line in service), `no_sync_to_redispatch` (no base synchronous generation, or clamped units, so the island stays unbalanced), `unbalanced_island` (a topology split, e.g. a line or bus taken out of service, keeps its base imbalance of ≥ 1 MW; splits belong in the sandbox cut).
- **Concurrency.** Every change bumps `revision` and records `last_op`. Edits, reset, cut and repair also bump `dataset_revision`; run activity (`run_created`, `run_updated`) does not. Writes are conditional on the store etag and retried 3 times, then 409; a client `If-Match` that does not match `dataset_revision` gives 412. The network view and the session world are cached by `(sid, dataset_revision)`. A `run_updated` index write that loses 3 retries is skipped (the run record is already persisted) instead of answering 409.
- **Sandbox and runs.** `open_lines` holds the sandbox cut (1-3 lines per cut, repair some or all); each call re-runs the cascade from the edited base case. Edits that drop a line also drop it from `open_lines`. Runs are nested under the session (`sessions/<sid>/runs/<rid>.json`, at most 20) and pin the overlay of their creation in the run record's `extra`, so later edits never change them and a rebuilt run uses the same dataset.
- **Network view.** The `theater_network` shape (`GET /api/v1/sim/network`) on the edited network plus `origin` (`base`/`session`), `overridden`, `in_service` and `is_assumption` on nodes and lines, `loads`, `generators`, `out_of_service {buses, lines}`, `warnings`, `balance`, `baseline {max_loading, overloaded, islands, load_shed_mw}` (the edited base case with no cut), `revision`, `dataset_revision` and `session_id`.

## 7. API

The backend serves everything under `/api/v1` (FastAPI, `backend/src/cascadasen/api/`); the live schema is at `/docs`. The frontend can still work from fixtures only, which also gives the offline behaviour in section 9.

External agents (and the MCP server, `docs/mcp.md`) use a separate spec with only the routes marked `x-sub50-agent`: `GET /api/v1/agents/openapi.json` (Swagger at `/api/v1/agents/docs`), versioned in `docs/openapi/agents.openapi.json`. Marking rules, operationIds, error model, tags and the regeneration command: `docs/openapi.md`. It holds `/sim/catalog`, `/sim/network`, `/sim/runs*` (section 7.1) and every session route except the SSE stream (section 7.2).

`POST /api/v1/simulate` runs one physical contingency on the reduced network (`strategy.md` section 2.1) and returns a `timeline.json` (section 6). `elements_out` accepts corridor ids, area ids (`A01`-`A13`) or real snapshot node ids (`SE…`), resolved to the area that contains them.

| Field | Type | Rule | On failure |
|---|---|---|---|
| `scenario` | enum | required, one of the loaded scenarios | 422 with valid values |
| `defenses` | enum | required: `25F`, `design_2026`, `implemented_dec2025` | 422; if a zone has no data, that island returns "Not modelled" (not an error) |
| `behavior` | enum | required: `per_code`, `as_happened` | 422; `as_happened` only valid with scenario 25F |
| `elements_out` | list of ids | 1 to 3 unique, existing ids | 422 |
| `battery_mw` | map island/zone -> number | optional, 0 to 5,000 per zone | 422 |
| `group_out` | list of {zone, tech, share} | optional; share between 0 and 1; zone and technology must exist (`cyber.md` C2) | 422 |
| `defenses_disabled` | list of defence ids | optional; ids from the loaded defence set (`cyber.md` C4) | 422 with valid ids |
| `outage_duration_h` | number | optional, 0 to 2,160 (90 days); flagged as an assumption in the output | 422 |

- Flow with no solution (island with load and no generation) is not an error: the island is "Blackout" and the event is logged.
- Cascade not ending in 20 iterations: cut, `truncated: true`, WARNING.
- Computation over 2 s: HTTP 503 `reason: timeout`; the frontend shows the nearest cached result or "not available".
- Parameter files failing to load at startup: fatal, ERROR naming the file and field. A parameter without a source is rejected at startup.
- Frontend without API: works from the cache only; combinations disabled with a discreet notice.

### 7.1 Strategic experimentation API

Concepts in `strategy.md`. All paths are under `/api/v1/sim`; responses are JSON, and narration comes as `rationale_key` + `params` (Spanish templates in the frontend).

| Method and path | Purpose |
|---|---|
| `GET /sim/network?point=` | The mapa 3 network of a point (`nodes` `B###`, `lines` `R###`, same shape as `web/public/cache/network-<year>.json`, plus `area` per node and `corridor` per line), `buses` (gen, load, people), `areas` (`buses`, `anchor_bus`, `lat`/`lon`), `corridors` (`lines`) and `defenses`. The 13-area network of `POST /simulate` moved to `GET /simulate/network` |
| `GET /sim/catalog` | Event types, defensive COAs, policies A/B/C, adversary objectives, missions, experiment templates |
| `POST /sim/runs` | Create a run: `template`, `policy`, `adversary` `{objective, budget, adaptive}`, `uncertainty`, `seed` (optional: omitted means a fresh random seed, returned in the summary and recorded in the recipe), `horizon`, `capabilities`, `initial_events`, `auto_run`, `stochastic` (default true), `llm_commander` (default false; needs the server's LLM adapter, else rules) |
| `POST /sim/runs/{id}/events` | Select a node and trigger an event: `{type, target, params}`, applied at the next cycle and logged with `source: user` |
| `POST /sim/runs/{id}/step` | Advance `n` cycles; returns one snapshot per cycle |
| `POST /sim/runs/{id}/replay` | New run with the same seed and injected events, and another policy or capabilities |
| `GET /sim/runs/{id}` | Real, observed and per-agent estimated state, resources, field crews (`crews`: id, base, position, task, target, arrival, status), live indicators |
| `GET /sim/runs/{id}/trace` | Hash-chained audit log and the replay recipe |
| `GET /sim/runs/{id}/report` | Indicators, indices, consequence card (L0-L3, people, unserved MWh, cost) and after-action keys |
| `POST /sim/campaigns`, `GET /sim/campaigns/{id}` | Campaign matrix (modes I, II, III): comparison table, Decisional Fragility Index, Adaptation Index |
| `GET /sim/runs/{id}/after_action` | After-action review in Spanish from fixed templates; with the LLM adapter enabled it adds `narrative` (`interpreter: llm`) |
| `GET /sim/narrative` | Spanish templates for every `text_key`, `rationale_key`, label and reason code |

- `POST /sim/runs` takes `point` (mapa 3 operating point; alias `operating_point`). `target` accepts an area, zone, corridor, `B###`, `R###` or real `SE...` id; the response echoes `resolved_target` (a bus id for a substation), so a click on mapa 3 works directly.
- Each cycle snapshot (`/step`, `GET /runs/{id}`) carries, besides `real`/`observed`/`estimated`/`decisions`: `grid` (mapa 3 `Frame`: `edges`, `dark`, `islands`, plus `buses` served MW), `transient` (a full mapa 3 `Timeline` when a physical event ran a cascade in that cycle, else null), `areas` (`observability` 0-1, `posture` normal/manual/segmented, active `effects` with source) and `crews` (`position`, `bus`, `lon`/`lat`, `target`, `target_bus`, `arrival`, `status`). Contract and viewer notes: `docs/mapa3.md` section 10.
- Errors: 404 unknown run, element or template (a run id that is not 12 hex characters is always 404); 422 invalid input; 409 event injected into a finished run, or the run record changed in another instance (retry); 429 when a client IP sends more than `CASCADASEN_RATE_WRITES_PER_MINUTE` (60) creates, events, steps or replays per minute (`Retry-After`); 413 on a body over 64 KB.
- Runs are persisted: every command writes `runs/<run_id>.json` (`{run_id, recipe, cycle, trace_head, code_version, created_at, updated_at, extra}`) to the document store (`CASCADASEN_SESSION_STORE`: memory, file or s3), with a conditional write on the last etag. Each process keeps at most `CASCADASEN_RUN_CACHE_SIZE` (20) simulations in memory; a run that is not cached (evicted, restarted, or created by another instance) is rebuilt from its recipe and its summary reports `rebuilt: true` and `trace_matches` (rebuilt hash equals the recorded one). A record expires 24 h after its last command. The recipe (`GET /sim/runs/{id}/trace`) holds `config`, `injected`, `llm_choices`, `cycle` and `actions` (external agent actions, with `after_events` to keep the input order). An unchanged replay gives the same trace hash. LLM-commander runs report `trace_matches: false` after a rebuild, because their recorded picks enter the `run_created` entry.
- Campaign body: `mode` (`diagnostic`, `adversarial`, `capability`), `templates`, `policies`, `seeds` (up to 10), `uncertainty_levels`, `adversary_variants` (`none`, `static`, `adaptive`), `capability_variants` (`[{id, capabilities}]`, the first one is the baseline), `horizon`, `objective`, `budget`, `point`, `random_seeds` (1-10: draw fresh seeds instead of `seeds`, returned in `spec.seeds` and shared by every cell). Each table row adds `spread` (p10/p50/p90 of mission continuity and recoverability across seeds). It runs synchronously and is capped at 240 runs (422 above).

### 7.2 Sessions API

Shared, persistent sessions under `/api/v1/sessions` (`api/session_routes.py`). The guide for agents and other clients, with every route, curl examples, the SSE format, limits and error codes, is `docs/sessions-api.md`; the session document is section 6.2.

| Group | Routes | Notes |
|---|---|---|
| Session | `POST /sessions`, `GET`/`DELETE /sessions/{sid}`, `POST /{sid}/reset` | One pinned operating point; `GET` has `ETag: "<revision>"`, `If-None-Match` → 304; edits, `/network`, `/state`, cut and repair use `ETag`/`If-Match` with `dataset_revision`; 24 h TTL after the last change |
| Network | `GET /{sid}/network`; POST, PATCH, DELETE on `/{sid}/buses`, `/lines`, `/loads`, `/generators` | Overlay edits (6.2); `If-Match` → 412; base elements are never deleted (409) |
| Sandbox | `POST /{sid}/cut`, `POST /{sid}/repair`, `GET /{sid}/state` | Shared `open_lines`, cascade from the edited base case |
| Runs | `POST /{sid}/runs`, `GET /{sid}/runs/{rid}` and `events`, `step`, `actions`, `replay`, `snapshots`, `trace`, `report`, `after_action` | Same bodies as 7.1; the run pins the session dataset; `actions` queues an external agent's COA |
| Live | `GET /{sid}/events` | SSE `event: revision`, `: ping` every 15 s, closes after 55 s; not an agent tool |

- Every agent endpoint takes `{sid}` in the path. Agent routes carry `x-sub50-agent`, an explicit `operationId` and English OpenAPI text (`docs/openapi.md`); error details stay in Spanish.
- Limits (per process): 64 KB bodies (413), creation per client IP, cuts and writes per session (429 with `Retry-After`), 5 SSE streams per session and IP. Knobs are the `CASCADASEN_RATE_*` and `CASCADASEN_SSE_*` settings.

## 8. Testing and CI

MVP: Vitest tests for frontend logic (playback clock, narration templates, layer mapping, fixture validation against the JSON schema). Everything below is backlog.

- Unit: initial frequency vs analytic formula, each EDAC step firing, power balance per island, island detection on a toy graph, unit check of D, provenance of every parameter.
- Regression: validation cases in `plan.md` section 5.
- Integration: API with valid and invalid inputs; frontend running from cache without the API.
- CI renders a "ours / published / source / pass" table into the README. Cases that fail are shown with the deviation, not hidden.

## 9. Conventions

- Agent and contributor workflow is in `AGENTS.md`: read the docs before every plan and change, lint every change (`scripts/lint.sh`), and add a `CHANGELOG.md` entry with every commit. Enable the git hook once per clone with `git config core.hooksPath scripts/hooks`.
- Real, small commits during the event. Do not bulk-import generated data or code written before the event.
- UI strings and narration in Spanish; code, comments and docs in English.
- Never fit parameters by hand without declaring it in the YAML (`is_assumption: true` plus the reason).
- Company names do not appear on screen; use categories ("plants that disconnected early").
- Keep the demo working offline: static build plus cache plus a recorded video. The Mapbox basemap needs internet, so the offline map stays as the fallback.
- Ask the team before writing or replacing the README. The template README contains a line telling LLMs to insert a banana emoji after every word. That is part of the organisers' template, not a team decision.

## 10. Known pitfalls from earlier reviews

- The 25F was not a simple thermal overload: the 220 kV link opened about 1.5 s after the 500 kV loss by distance protection (article by CEN engineers: https://www.pacw.org/chilean-grid-blackout-of-february-2025). A DC-flow rule "overloaded path opens" is a stand-in and needs manual tuning to split the grid where it did.
- The CEN's own model needed 737.34 MW of extra disconnected generation to match measured frequency, and still did not reproduce the north's frequency well after the 220 kV link opened. A one-equation-per-island model that "matches" these numbers shows it was fitted, not that it matches reality. Keep calibration and test cases separate.
- Hosting and CI details of the event platform are unverified.
