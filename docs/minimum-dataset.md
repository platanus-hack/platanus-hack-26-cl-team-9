# Minimum dataset and cut propagation

For whoever modularises the simulator. Two questions:

1. Which attributes does the engine need to simulate a cut, an overload and the people affected? Everything else is "data" and sits behind a filter.
2. What happens in the code, step by step, when a line is cut?

Tags: EVIDENCE = read from code or files in this repo. ASSUMPTION = modelling choice or inference, not verified.

Related: `docs/engine.md` (physics), `docs/mapa3.md` (viewer and actors).

## 1. The minimum dataset

### 1.1 Engine inputs (the simulation breaks without these)

**Per node** (one per substation, 188 in 2025 and 2026). Python: `ReducedNetwork` in `network.py` and `OperatingPoint` in `scenario.py`.

| Attribute | Type | Used for | Used by |
|---|---|---|---|
| `id` (`B000`...) | string | Key everywhere | all |
| `lat` | float | Zone: `norte_grande` if north of -26.0, else `centro_sur` | `network.zone()`, EDAC tables |
| `gen` (MW) | float | Net injection = `gen - load`, input of DC flow | `flow.dc_flow`, `engine._settle_islands` |
| `load` (MW) | float | Net injection, shed by EDAC, lost if the island dies | `flow`, `frequency`, `engine._timeline` |
| `sync_mw` | float | Primary reserve (4% of it) and the synchronous/non-synchronous split | `frequency.simulate_island` |
| `inertia_mws` | float | Speed of the frequency fall (`E` in the swing equation) | `frequency.simulate_island` |
| `people` | float | Only the "people without power" figure | `engine._timeline` |

**Per line** (273 in 2025 and 2026). Python: `Line` in `network.py`.

| Attribute | Type | Used for |
|---|---|---|
| `id` (`R000`...) | string | What the user cuts. File name of the cached result |
| `a`, `b` | bus index | Graph edges: islands and flow |
| `x_pu` | float | Splits the flow among lines (DC flow). Floor 5e-4 pu |
| `capacity_mw` | float | Overload ratio = `abs(flow) / capacity_mw`, trips above 1.2 |

**Model parameters** (`Params` in `engine.py` and `frequency.py`). ASSUMPTION unless noted.

| Parameter | Value | Note |
|---|---|---|
| `overload_factor` | 1.2 | Line opens above 120% of capacity |
| `stage_spacing_s` | 1.0 | Illustrative time between stages |
| `max_stages` | 20 | Safety stop |
| `local_cut_mw` | 200 | Island with no inertia and under this load counts as `local_cut`, else `blackout` |
| `reserve_share_of_sync` | 0.04 | Reserve = 4% of online synchronous MW |
| `reserve_full_at_hz`, `reserve_time_constant_s` | 0.3, 3.0 | Reserve response |
| `load_damping_pct_per_hz` | 1.5 | Load falls with frequency |
| Blackout band | 47.5 to 52.0 Hz | EVIDENCE for 47.5 (CEN 25F report). 52.0 is ASSUMPTION |
| EDAC tables | `CENTRO_SUR_*`, `NORTE_GRANDE_STEPS` | EVIDENCE: CEN 25F report |

That is all. Per node: 7 attributes. Per line: 5. A node's name, voltage level, coordinates (other than latitude for the zone) and owner are not inputs.

### 1.2 Engine outputs (what the viewer reads)

Timeline per `(point, cut)`, written to `web/public/cache/<point>/<line id>.json`:

| Key | Content |
|---|---|
| `events[]` | `t`, `type`, `ids`, `text_key`, `params`. The viewer turns them into Spanish with fixed templates (`text.ts`) |
| `frames[]` | One per stage: `edges{id: {flow_mw, status, loading}}`, `dark[]` (bus ids), `islands[]` |
| `frequency_hz` | Curve per island |
| `summary` | `people_without_power`, `load_shed_mw`, `load_total_mw`, `stages`, `lines_opened`, `dark_buses`, `islands[]` |
| `assumptions` | Strings shown in the panel |

People without power = sum over buses of `people * (1 - load_final / load_initial)` (EVIDENCE: `engine._timeline`). So `people` only scales with the share of load lost. A bus with load and `people = 0` contributes nothing to the figure.

### 1.3 Drawing attributes (needed to show, not to simulate)

`name`, `kv` (line width and tooltip), `lon`, `lat`, `map_nodes`, `map_edges`, `branches`. They live in `network-<year>.json`.

### 1.4 Data under the filter

These attributes exist in `data/processed/node_index.json` (the node dictionary, built for the popup). The engine does not read that file. EVIDENCE: nothing under `backend/src/cascadasen/domain/cascade/` opens `node_index.json`.

Where the engine gets its inputs instead (EVIDENCE: `scenario.py`, `network.py`):
- `data/processed/grid_snapshot.json`: `model_buses` and `model_branches` (build the 188 nodes and 273 lines) and `comunas[].served_by` (population, becomes `people`).
- `data/processed/operating_points.json`: `load_by_bus`.
- `data/processed/baseline_opf.json`: `gen_by_bus`, `sync_mw_by_bus`, `inertia_by_bus_mws`.

The raw comuna names, owners and line kilometres in `node_index.json` are therefore pure display data. The comuna populations in `grid_snapshot.json` are not: they feed the people figure.

| Group | Attributes |
|---|---|
| Node identity | `owner`, `system`, `segment`, `macro_zone`, `region_code`, `comuna_code`, `kind`, `kv_levels`, `in_main_grid`, `degree`, `delivers`, `cen.*` |
| Node supply | `plants[]` (per plant), `plants_count`, `generation_mw`, `storage[]`, `storage_candidates` |
| Node population | `comunas[]`, `served_population` |
| Node lines | `lines[]`: `km`, `mva`, `x`, topology source, assumption flag, circuit |
| Node model | `model_buses[]`, `model_branches[]` |
| Operating | `operating{point: [load, gen]}` |

How it is filtered now (web, branch `feature/minimal-tooltips`):

| Place | Always visible | Behind "Ver todos los datos" or collapsed |
|---|---|---|
| Node popup (mapas 1 and 2, `map/nodeDetail.ts`) | Name, id, kV levels, people served, number of lines, generation MW, simulated demand and dispatch | Ficha, storage, population by comuna, connected lines, PyPSA-CL model |
| Mapa 3 substation tooltip | Name, kV, demand MW, people, "Sin energía" | Nothing hidden |
| Mapa 3 line tooltip | Name, flow MW, % of capacity | Nothing hidden |
| Mapas 1 and 2 tooltips | Name, kV (or MW and technology for plants) | Nothing hidden |
| Mapa 3 side panel | Hour selector, result numbers, player, events, frequency chart | Legend and model assumptions (both collapsed) |

Where the filter lives in code:
- `_card()` in `web/src/map/nodeDetail.ts`: the first group of sections is the minimum, the `extra` container is the filtered part. To move an item between them, move it in that function.
- `Legend.tsx` in `web/src/cascade/`: a `<details>` element.
- ASSUMPTION: the filter is a button per popup, not a global setting. A single global switch for all maps was not built.

### 1.5 Known data defect (affects the people figure, not the physics)

EVIDENCE: at `feb2025-1500`, 23 substations with more than 20 MW of demand have `people = 0`. Together they hold 2,412 of 11,096 MW (22%). The model total is 18.16 M people against 15.2 M reported for the 25F. ASSUMPTION: the cause is the comuna-to-substation mapping in `scenario._people` (each comuna goes to the bus nearest the node that serves it). Not investigated. Treat "people without power" as a lower-bound estimate until fixed. MW figures are not affected.

## 2. What happens when the network is cut

Entry point: `run_cascade_workflow(net, point, cut_line_ids)` in `engine.py`. Offline, `cache_builder.py` calls it once per line and per hour (273 x 4) plus once without a cut. The browser never runs it.

### 2.1 Sequence

```
run_cascade_workflow(net, point, cut_ids)
 1. _start            copy gen, load, sync, inertia. open_lines = cut_ids. Event "line_cut" at t = 0.
 2. loop stage = 0..20, t = stage * 1.0 s
    a. find_islands(net, open_lines)            union-find over lines not open -> list of bus groups
    b. _settle_islands                          per NEW island (not seen before): frequency outcome
         island has no gen or no load      -> _lose_island (dark)
         no inertia or no sync MW          -> local_cut (< 200 MW) or blackout
         |gen - load| < 1 MW               -> maintains, no simulation
         otherwise  simulate_island        -> maintains or blackout (+ EDAC steps)
         maintains: _shed_load, _share_reserve change gen and load of the island
         blackout:  _lose_island sets gen, load, sync, inertia to 0 and adds buses to `dark`
    c. dc_flow(net, open_lines, gen - load, islands)   flows in MW per line, per island
    d. _frame                                   snapshot: edges, dark, islands
    e. _most_overloaded                         lines at the worst ratio, if worst > 1.2
         none -> stop (cascade ended)
         some -> add to open_lines, event "line_overload_open" at t + 1.0 s, next stage
 3. _timeline         summary, people, events sorted by time
```

### 2.2 Which state each step reads and writes

| State (in `_State`) | Written by | Read by |
|---|---|---|
| `open_lines` | `_start` (the cut), step 2e (overload trips) | `find_islands`, `dc_flow`, `_frame` |
| `gen`, `load` | `_shed_load`, `_share_reserve`, `_lose_island` | `_settle_islands`, `dc_flow` input, `_timeline` |
| `sync`, `inertia` | `_lose_island` | `_settle_island`, `_island_input` |
| `dark` | `_lose_island` | `_frame`, `_timeline` |
| `results` (island -> outcome) | `_settle_islands` | prevents settling the same island twice |
| `events`, `curves`, `frames` | all steps | `_timeline` |

### 2.3 Consequences you can predict

- Cutting a line changes only `open_lines`. Everything else follows from the graph and the injections.
- If the cut does not split the graph, there is no island change. Flows redistribute by `x_pu` (step 2c). If every line stays under 120%, the cascade stops at stage 0. EVIDENCE: 219 to 238 of the 273 cuts have no effect, depending on the hour.
- If the cut splits the graph, each side is an island with its own slack bus (`dc_flow` picks the bus with the largest absolute injection). Each side gets its own frequency simulation. The side with deficit sheds load through EDAC or collapses. The side with surplus curtails non-synchronous generation above 50.2 Hz.
- A collapsed island zeroes its gen, load, sync and inertia. Its buses join `dark`. Lines inside it carry no flow (no injection), so they stop overloading.
- After an island settles, its injections changed (shedding, reserve, curtailment), so the flows in the next stage differ from the first estimate. This is why lines can open in later stages.
- The loop is monotone: `open_lines` only grows and an island is settled once. That bounds the run to at most 20 stages.

### 2.4 Worked case

EVIDENCE (engine output, `feb2025-1500`, cut `R239` Nueva Maitencillo-Nueva Pan de Azúcar 500 kV, 2,210 MVA):

| t | Step | Result |
|---|---|---|
| 0.0 s | 2a, 2b | One island of 188 buses, 11,096 MW gen and load, stable |
| 0.0 s | 2c, 2e | Flow redistributes after the cut. Pan de Azúcar-Punta Colorada 220 kV exceeds 120% |
| 1.0 s | 2e | Pan de Azúcar-Punta Colorada opens. Flow redistributes again |
| 2.0 s | 2e | Maitencillo-Pan de Azúcar 110 kV exceeds 120% and opens. The graph splits |
| 2.0 s | 2a, 2b | Island of 115 buses (5,667 MW gen, 7,872 MW load) and island of 73 buses (5,428 MW gen, 3,223 MW load) |
| 2.3 s onward | `simulate_island` | The deficit island sheds load by EDAC and its frequency falls under 47.5 Hz. The north has a surplus (ASSUMPTION: it curtails non-synchronous generation only if its frequency passes 50.2 Hz) |
| End | `_timeline` | 7,872 of 11,096 MW lost, 15.2 M people |

Not computed: the voltage collapse in the north that the CEN report describes.

## 3. Seams for modularisation

Boundaries that already exist (EVIDENCE):

| Module | Pure function of | Replaceable by |
|---|---|---|
| `network.reduce_network` | grid snapshot, year | Any graph builder that returns `ReducedNetwork` |
| `scenario.load_operating_point` | processed JSON files | A live feed or another dataset, if it fills `OperatingPoint` |
| `flow.find_islands`, `flow.dc_flow` | `net`, `open_lines`, injections | AC power flow, as long as it returns MW per line |
| `frequency.simulate_island` | `IslandInput`, `Params` | Another frequency model. It returns `IslandResult` |
| `engine.run_cascade_workflow` | the three above | Orchestration only |
| `cache_builder` | the engine | A live API (`stack.md` plans FastAPI) |
| `web/src/cascade/*` | cache JSON files only | Any frontend. The files are the contract |

Coupling to be aware of (ASSUMPTION: these are the likely pain points for a refactor):
- `engine._State` is a mutable bag shared by `_settle_islands`, `_shed_load`, `_share_reserve` and `_lose_island`. Splitting them needs an explicit state object passed through.
- Zone (`norte_grande` or `centro_sur`) is derived from latitude in `network.py` and selects EDAC tables in `frequency.py`. Adding a zone means touching both files.
- Bus ids are positional (`bus_id(i)` = `f"B{i:03d}"` in `domain/cascade/network.py`, used by `engine._frame` and `cache_builder`). If the network order changes, ids change and the cache must be rebuilt.
- The cache is the only contract with the frontend. Changing a key in the timeline breaks `types.ts`, `text.ts` and `CascadeApp.tsx` together.
- `people` comes from `scenario._people`, outside the physics. It can be replaced without touching the engine, as long as the output stays one value per bus.

## 4. How to check you did not break it

```bash
cd backend && PYTHONPATH=src python -m pytest tests -q          # 41 tests, 11 in test_cascade.py
cd web && npx tsc --noEmit && npm test && npm run build
```

Regression anchor: after any engine change, the 25F cut (`feb2025-1500`, `R239`) should still give 2 stages, 11,096 of 11,096 MW lost, about 18.2 M people (every person the model assigns; 16.8 M before issue #90 counted dark buses with net load at or below zero) and two islands that collapse by voltage at 2.0 s (re-measured 2026-11-22; the 3.8 M people of 2026-11-21 came from the extreme-contingency EDAC, now removed). Test: `test_loaded_25f_corridor_cut_collapses_both_ends_by_voltage`. If it does not hold, the change altered behaviour. Decide whether that is intended, then update `docs/engine.md`.
