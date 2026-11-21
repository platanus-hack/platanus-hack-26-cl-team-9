# Changelog

Written for agents. Newest entry first. Each commit adds one entry at the top, using the format in `AGENTS.md` section 3. Read the newest entries before planning or changing anything. They record what changed after the docs were written.

## 2026-11-21 · docs(agents): pending work of the physical bots

- **Changed:** `docs/agents.md` section 4 is now a table of pending work: LLM commander physical context, operation view drawing the readings, releasing reserve and batteries, regenerating the map cache, the repeating `low_inertia` alarm, the per-island inertia floor, and V2–V9 calibration on the 188-bus network.
- **Why:** Ricardo asked to keep the "not done yet" items written down.
- **Agents:** Pick pending work from `docs/agents.md` section 4 and remove the row when it is done.
- **Files:** `docs/agents.md`.

## 2026-11-21 · feat(agents): bots read frequency, rocof, inertia and voltage-limited islands

- **Changed:** `AreaObs` gains `freq_hz` and `rocof_hz_s`, filtered by supervision (missing → `None`, stale or unreliable → a normal 50 Hz, fresh → noise `digital.freq_noise_hz`). New alarms: `frequency_out_of_band` (49.0–51.0 Hz), `high_rocof` (≥ 1 Hz/s), `low_inertia` (island below 31,000 MWs after losing units) and `voltage_limited`; thresholds in `theater.yaml` → `physics_alarms` (`TheaterConfig.physics_alarms`, merged into `digital`). ISR weighs them as physical evidence. Stabilisation proposes batteries on steep RoCoF or lost inertia, reserve under frequency, and load reduction when nothing is left; it vetoes restorations into out-of-band or voltage-uncertain islands and a controlled islanding next to a low-inertia island. New `docs/agents.md` holds the bots' physical contract; `strategy.md`, `stack.md` 4.6 and `AGENTS.md` (read order) point to it.
- **Why:** Ricardo (2026-11-21): the bots must work on the physics of the power-system review (operating band, RoCoF, inertia that falls, voltage documented and not computed), not only on MW.
- **Agents:** Read `docs/agents.md` before touching `domain/agents/` or `theater/digital.py`. New rationale keys `stab_fast_support_low_inertia`, `stab_reserve_under_frequency`, `stab_voltage_uncertain`, `stab_low_inertia` (Spanish text in `narrative_es.yaml`). The snapshot's `observed.areas` carries `freq_hz`/`rocof_hz_s`; the web does not draw them yet. Open: the LLM commander context has no physical summary yet (`cycle.py`/`llm.py` were being edited in parallel on `feat/strategic-sim-api`). `AdversaryView` must stay free of physical fields (test).
- **Files:** `backend/src/cascadasen/domain/agents/{stabilization,isr}.py`, `backend/src/cascadasen/domain/theater/{state,digital,config}.py`, `backend/src/cascadasen/domain/theater/params/{theater,narrative_es}.yaml`, `backend/tests/unit/test_physical_bots.py`, `docs/agents.md`, `docs/strategy.md`, `docs/stack.md`, `AGENTS.md`.

## 2026-11-21 · feat(theater): real islands, battery pool and frequency per area

- **Changed:** `TheaterGrid` keeps `battery` per area apart from `extra_reserve` (passed to the engine as `battery_by_bus`, 200 ms + 300 ms response) and reads the engine's settled islands into `freq_hz`, `nadir_hz`, `rocof_hz_s` and `island_result` per area, plus `last_islands` (area lists). `settle_frequency()` puts energized areas back at 50 Hz at each `Executor.tick` (secondary control, assumption). `island_inertia_mws(area)` is new. `last_transient["islands"]` now lists the engine's real islands touching hit areas, with `min_hz`, `final_hz`, `rocof_hz_s`, `inertia_mws`; `voltage_limited` maps to `uncertain` and `last_transient["uncertain"]` takes the engine summary.
- **Why:** The bots need physical readings per area (docs/agents.md); the old `islands` entry was one synthetic island and `uncertain` was always false.
- **Agents:** `battery_support` now fills `grid.battery`, not `extra_reserve`. Reserve and battery blocks stay held until the area blacks out (no release yet; `restoration.reserve_recovery` is still unused).
- **Files:** `backend/src/cascadasen/domain/theater/{grid,execution}.py`.

## 2026-11-21 · feat(cascade): provenance params, droop, batteries, extreme EDAC and voltage verdict

- **Changed:** The cascade engine (188 buses, drives the theatre and the map cuts) reads every number from `domain/cascade/params/cascade.yaml` (source or `is_assumption`, same loader as `domain/simulation/params.py`). Frequency model: reserve with 5% droop capped at 4% of synchronous MW; batteries as a separate fast term (`IslandInput.battery_mw`, trigger 49.8 Hz, 200 ms delay, 300 ms ramp); extreme-contingency EDAC of the centro-sur (671.55 MW, three df/dt stages). Each island reports `final_hz`, `rocof_hz_s`, `inertia_mws`, `shed_mw` and `battery_mw`; `CascadeState.islands` adds the bus indices. Opening the 25F boundary with a pre-fault flow above 1,600 MW N→S / 1,000 MW S→N gives `result: "voltage_limited"` and `summary.uncertain: true`. Fix: deployed reserve now also counts as synchronous (the theatre classed it as renewable).
- **Why:** Power-system review (2026-11-21): inertia that falls, EDAC from the CEN tables, batteries as fast injection, honest about voltage, every parameter traceable. First step before the agents read frequency.
- **Agents:** Do not hardcode physics constants in `domain/cascade/`; add them to `cascade.yaml` with provenance. `run_cascade_state(..., battery_by_bus=...)` is new. Timeline `summary` gains `uncertain` and `prefault_boundary_mw`; island entries gain fields (additive, `web/src/cascade/types.ts` still reads). The V1 split holds on this network without tuning (1,905 / 287 MW, test `test_25f_prefault_split_matches_the_cen_report`). `web/public/cache/` is stale until `uv run cascadasen-cache` runs again.
- **Files:** `backend/src/cascadasen/domain/cascade/{params/cascade.yaml,frequency.py,engine.py}`, `backend/tests/unit/test_cascade.py`, `docs/engine.md`.

## 2026-11-21 · feat(llm): any Bedrock model through the Converse API

- **Changed:** New provider `CASCADASEN_LLM_PROVIDER=bedrock-converse`: `infrastructure/llm.py` calls `bedrock-runtime` `converse` (boto3) with the model or inference-profile id as is (`CASCADASEN_LLM_MODEL`, e.g. `amazon.nova-pro-v1:0`). The JSON answer is a forced tool call with the schema; on `ValidationException` (model without forced tools) it retries with the schema in the prompt and parses the text. Same AWS credential chain (environment variables or profile). README: provider docs and a script that lists the Bedrock models the account can actually call.
- **Why:** Ricardo's AWS account (402909940511) has no Claude model available on Bedrock ("not available for this account"); the LLM commander should work with another model.
- **Agents:** Prompts and fallbacks are unchanged; any failure still falls back to the rules (`llm_unavailable`). Quality of C2 picks depends on the chosen model; the validator still filters every option first.
- **Files:** `backend/src/cascadasen/infrastructure/{llm,settings}.py`, `backend/tests/unit/test_llm_commander.py`, `backend/README.md`.

## 2026-11-21 · fix(llm): Bedrock with temporary AWS environment credentials

- **Changed:** An empty `CASCADASEN_AWS_PROFILE`/`CASCADASEN_AWS_REGION` now means "not set", so `AnthropicBedrockMantle` uses the standard AWS chain (environment variables first). `docker-compose.yml` passes `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` and `AWS_REGION` through to `backend` when set on the host. README and docker docs explain both options (environment variables or a profile).
- **Why:** Ricardo authenticates with the SSO portal's "Set AWS environment variables" (temporary credentials in the shell), not with a named profile.
- **Agents:** A profile set in `.env` takes precedence over the environment variables; leave it out when using variables. The variables must be exported in the terminal that runs `cascadasen-api` (or compose) and expire with the SSO session.
- **Files:** `backend/src/cascadasen/infrastructure/llm.py`, `docker-compose.yml`, `backend/README.md`, `docs/docker.md`.

## 2026-11-21 · docs(web): operation mode of mapa 3

- **Changed:** `docs/mapa3.md` section 10 now describes the implemented operation tab (user flow, offline behaviour); `web/README.md` gets a "Operation mode (mapa 3 + backend)" section with the commands to run API, caches and Vite.
- **Why:** Close the frontend-backend integration with instructions to test it.
- **Agents:** Keep `mapa3.md` section 10 in sync with `web/src/operation/` and `cycle._snapshot`.
- **Files:** `docs/mapa3.md`, `web/README.md`.

## 2026-11-21 · feat(llm): Amazon Bedrock provider with an AWS profile

- **Changed:** `Settings` gains `llm_provider` (`anthropic` | `bedrock`), `aws_region` and `aws_profile` (`CASCADASEN_LLM_PROVIDER`, `CASCADASEN_AWS_REGION`, `CASCADASEN_AWS_PROFILE`). With Bedrock, `infrastructure/llm.py` builds `anthropic.AnthropicBedrockMantle(aws_profile, aws_region)`, prefixes the model (`anthropic.claude-opus-5-5`) and sends no `betas`/`fallbacks` (not supported on Bedrock); structured JSON output stays. A client that cannot be built (e.g. unknown profile) disables the LLM with a warning. Extra `llm` is now `anthropic[bedrock]` (adds boto3); `uv.lock` updated. Docker: optional `WITH_LLM=1` build arg, `backend/.env` as optional `env_file`, commented `~/.aws` read-only volume.
- **Why:** Ricardo runs the LLM through Bedrock with an AWS profile; credentials stay in `~/.aws`, never in `.env`.
- **Agents:** `backend/.env` holds settings only. Tests build `Settings(_env_file=None, ...)` so a developer's `.env` cannot change them. No test calls AWS.
- **Files:** `backend/src/cascadasen/infrastructure/{llm,settings}.py`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`, `docker-compose.yml`, `backend/tests/unit/test_llm_commander.py`, `backend/README.md`, `docs/strategy.md`, `docs/docker.md`.

## 2026-11-21 · feat(web): operation tab in mapa 3 (theatre on the map)

- **Changed:** Mapa 3 has two tabs: "Corte" (unchanged cut viewer) and "Operación" (`?modo=operacion`). New `web/src/operation/OperationPanel.tsx`: pick scenario, defence policy and adaptive or static adversary; start a run (seed shown); play or step 5-minute cycles; the map draws the cycle's grid, areas and crews; "Ver cascada" replays the cycle's cascade in seconds with its events and frequency chart; click a line to open it (C3) or a substation for C1/D1/D4 next cycle; final report and after-action; repeat with the same seed and another policy. `CascadeApp` delegates layers, clicks and tooltips to the active tab through a `MapBridge` ref; `FrequencyChart` moved to `cascade/FrequencyChart.tsx`. Styles for tabs and the panel.
- **Why:** Join the frontend with the theatre (approved plan).
- **Agents:** Offline (no backend) the tab plays the precomputed runs and refuses events. Verified through the Vite proxy against the real API (R239 on `feb2025-1500` gives 15.2 M people, same as the cut viewer); `tsc`, `npm test` (19) and `npm run build` pass. Not verified by clicking in a browser here.
- **Files:** `web/src/operation/OperationPanel.tsx`, `web/src/cascade/CascadeApp.tsx`, `web/src/cascade/FrequencyChart.tsx`, `web/src/styles.css`.

## 2026-11-21 · feat(web): operation layers for mapa 3 (areas, crews, effects)

- **Changed:** New `web/src/operation/layers.ts`: `buildOperationLayers` reuses `buildCascadeLayers` with the cycle's frame and served load per bus, and adds operating areas (circle at the centroid, posture colour, more opaque as observability drops), effect labels per area (effect type only) and field crews moving linearly toward their target substation by cycle. Colour constants `POSTURE_COLOR`, `CREW_COLOR`, `CREW_BUSY_COLOR` for map and legend. Tests in `layers.test.ts`.
- **Why:** Draw the theatre on mapa 3 with the same visual language as the cut viewer.
- **Agents:** Areas are drawn as circles: the backend sends no area polygons. No layer shows adversary preferences or any ranking.
- **Files:** `web/src/operation/layers.ts`, `web/src/operation/layers.test.ts`.

## 2026-11-21 · feat(web): theatre client for the mapa 3 operation mode

- **Changed:** New `web/src/operation/`: `types.ts` (theatre contract of `docs/mapa3.md` 10 over the mapa 3 types), `api.ts` (`TheaterSource` with `LiveSource` over `/api/v1/sim/*` and `CachedSource` over `web/public/cache/theater/`; `connect()` picks live when `/api/v1/health` answers within 1.5 s), `text.ts` (Spanish narration from the backend templates, fixed notice). Tests: `api.test.ts`, `text.test.ts`. Backend: new `GET /api/v1/sim/runs/{id}/snapshots?start=` because a replay computes all its cycles at once.
- **Why:** First step to join the frontend with the theatre (approved plan: operation tab in mapa 3).
- **Agents:** The frontend never hard-codes the backend URL (Vite proxy). Offline runs cannot inject events; "repeat with another policy" switches to the precomputed run of that policy.
- **Files:** `web/src/operation/*`, `backend/src/cascadasen/application/run_experiment.py`, `backend/src/cascadasen/api/simulation_routes.py`, `backend/tests/integration/test_runs_api.py`.

## 2026-11-21 · chore(web): proxy /api to the backend for the mapa 3 operation mode

- **Changed:** `web/vite.config.ts` proxies `/api` to `VITE_API_TARGET` (default `http://localhost:8000`). `docker-compose.yml` sets `VITE_API_TARGET=http://backend:8000` for `web` and starts it after `backend` is healthy. `docs/docker.md` no longer says the web never calls the backend.
- **Why:** The operation mode of mapa 3 (theatre on the map) calls `/api/v1/sim/*`.
- **Agents:** Frontend code calls relative `/api/v1/...` paths; never hard-code the backend URL.
- **Files:** `web/vite.config.ts`, `docker-compose.yml`, `docs/docker.md`.

## 2026-11-21 · merge main into feat/strategic-sim-api (mapa 3 as main map, 2D/3D, attack-sim proposal)

- **Changed:** Brings #14-#19 (mapa 3 is `/`, 2D/3D toggle `?vista=2d`, city labels, Sub50 project metadata) and `docs/attack-sim.md`. `CHANGELOG.md` conflict resolved keeping both sides. Follow-ups: `mapa3.md` section 10 now says the operation mode lives in `/` and that `buildCascadeLayers` takes `mode` (draw `snapshot.grid` with the same 2D/3D mode); `stack.md` section 2 map row updated (it still said `/` was the offline map); `attack-sim.md` gets a note on its overlap with the theatre's event API.
- **Why:** Ricardo: main changed the map; check what the theatre must adapt.
- **Agents:** No backend or contract change was needed: the cut cache format and `web/src/cascade/types.ts` are unchanged, and theatre snapshots already use the mapa 3 `Frame`. `attack-sim.md` is a proposal pending team decision; if approved, build it on `POST /sim/runs/{id}/events` (C1 on `B###`, C2 by zone, C3 on `R###`).
- **Files:** `CHANGELOG.md`, `docs/mapa3.md`, `docs/stack.md`, `docs/attack-sim.md`.

## 2026-11-21 · docs(theater): document the theatre on the mapa 3 network

- **Changed:** `strategy.md` 2.1 (areas = groups of the 188 mapa 3 buses, corridors, EDAC defence functions, mapa 3 points), `stack.md` 7.1 (`/sim/network?point=`, `point`, snapshot `grid`/`transient`/`areas`/`crews`, `/simulate/network`, campaign `point`), `mapa3.md` new section 10 (operation-mode contract with TS types for the frontend), `plan.md` 9 item 4 (node decision), `backend/README.md`.
- **Why:** The frontend teammate builds the operation mode on mapa 3 against this contract.
- **Agents:** `mapa3.md` section 10 is the frontend contract; keep it in sync with `cycle._snapshot` and `SimulationService.theater_network`.
- **Files:** `docs/strategy.md`, `docs/stack.md`, `docs/mapa3.md`, `docs/plan.md`, `backend/README.md`.

## 2026-11-21 · feat(theater): offline theatre cache for mapa 3

- **Changed:** `cascadasen-sim-fixtures` now writes `web/public/cache/theater/` (git-ignored, next to the mapa 3 cut cache): `index.json`, `catalog.json`, `narrative_es.json`, `network-<point>.json`, `<point>/flagship_observability-<A|B|C>-s<seed>.json` (recipe, snapshots, report, after-action) and `campaign-<point>.json`, for `nov2026-1300` and `feb2025-1500` by default. Campaigns accept `point` (`CampaignSpec.point`, `POST /sim/campaigns`).
- **Why:** The live API gives a new random run each time; the demo needs a fallback without a server.
- **Agents:** Options `--point` (repeatable), `--seed` (default 7), `--no-campaign`, `--out`; `build_theater_cache(..., template=)` for other templates. About 0.9 MB per run. The old 13-area fixtures (`data/processed/sim/`, 25F timelines of `/simulate`) are no longer written.
- **Files:** `backend/src/cascadasen/sim_fixtures.py`, `application/run_campaign.py`, `api/simulation_{routes,schemas}.py`, `backend/tests/integration/test_theater_cache.py`.

## 2026-11-21 · refactor(theater): run the strategic theatre on the mapa 3 network

- **Changed:**
  - New `domain/theater/areas.py` (`TheaterNetwork`): the 13 operating areas are groups of the 188 mapa 3 buses by latitude band; corridors are the `R###` lines crossing area boundaries (`A06-A07`); defence functions are `edac:norte_grande` and `edac:centro_sur`. `resolve` accepts area, zone, corridor, `B###`, `R###` and real `SE...` ids.
  - New `domain/theater/grid.py` (`TheaterGrid`): per-bus state (plan vs current load, sync/renewable generation, inertia, open lines, dark buses, disabled EDAC zones, extra reserve) with area reads and explicit writes; physical events run `run_cascade_state` (mapa 3 engine). `frame()` gives the mapa 3 `Frame` of each cycle.
  - New `domain/theater/world.py` (`TheaterWorld`, `StaticWorld`) and `application/theater_world.py` (`ProcessedWorld` over `data/processed`). `Simulation(world, config)`; `RunManager`/`CampaignRunner` take a world. Templates use mapa 3 points (`nov2026-1300`) and the new corridor/defence ids; `pdce_zn` and the `defenses` option are gone (one defence set: `cen_25f_edac`).
  - Snapshots add `grid` (mapa 3 frame + served MW per bus), `transient` (full mapa 3 cascade timeline when a physical event happened), `areas` (observability, posture, effects) and crews with `bus`, `lon`, `lat`, `target_bus`. `GET /api/v1/sim/network?point=` serves the mapa 3 network plus areas, corridors and defences; the old 13-area view moved to `GET /api/v1/simulate/network`. `POST /sim/runs` accepts `point`.
- **Why:** Ricardo: mapa 3 is the important view; one physics so the theatre's MW, dark buses and open lines are what the viewer draws.
- **Agents:** The theatre no longer uses `domain/simulation` physics (only its params loader and the area bands). Campaigns run with `light=True` (no per-cycle frame): 36 flagship runs take about 9 s. Flagship on `nov2026-1300`, seed 7, static adversary: C keeps the most continuity, B makes the most unnecessary decisions (test still holds). The adversary never targets `B###`/`R###` (tested). `cascadasen-sim-fixtures` still needs porting (next commit).
- **Files:** `backend/src/cascadasen/domain/theater/{areas,grid,world,execution,validator,digital,cycle,state,config,crews}.py`, `params/templates.yaml`, `domain/agents/*.py`, `application/{theater_world,run_experiment,run_campaign,simulation_service}.py`, `api/simulation_{routes,schemas}.py`, `backend/tests/**`.

## 2026-11-21 · feat(cascade): run the cascade from a running state

- **Changed:** New `run_cascade_state(net, point, cuts, params, *, open_lines, edac_off, extra_reserve_by_bus)` returns the timeline plus a `CascadeState` (per-bus gen, load, sync, inertia, open lines, dark buses). `IslandInput.extra_reserve_mw` adds fast reserve to an island. `run_cascade_workflow` is now a thin wrapper with identical output (checked on 162 real cuts across two points).
- **Why:** The strategic theatre is being ported onto the mapa 3 network; it needs to continue a cascade cycle after cycle, switch EDAC zones off (C4) and commit fast reserve or batteries.
- **Agents:** Mapa 3 and `cascadasen-cache` are unchanged. EDAC zones are `norte_grande` and `centro_sur`.
- **Files:** `backend/src/cascadasen/domain/cascade/engine.py`, `frequency.py`, `backend/tests/unit/test_cascade.py`.

## 2026-11-21 · merge main into feat/strategic-sim-api (mapa 3, cascade engine)

- **Changed:** Brings mapa 3, `domain/cascade/` and `cascadasen-cache` from main (#10-#12). Conflicts in `CHANGELOG.md` and `backend/pyproject.toml` resolved keeping both sides. Lint-only fixes on the merged files so the pre-commit hook passes: `ruff format`, unused imports, sorted imports, `zip(..., strict=True)` in `cascade/engine.py`, executable bit on `data/scripts/*.py`. No behaviour change (126 tests pass).
- **Why:** Ricardo: mapa 3 is the important view; the theatre must be ported onto its network next.
- **Agents:** Two physics engines now coexist: `domain/cascade/` (188 buses, mapa 3) and `domain/simulation/` (13 areas, theatre and `/simulate`). The approved plan ports the theatre onto `domain/cascade/`.
- **Files:** `backend/src/cascadasen/domain/cascade/*`, `backend/src/cascadasen/application/cache_builder.py`, `backend/tests/unit/test_cascade.py`, `data/scripts/*.py`, `backend/pyproject.toml`, `CHANGELOG.md`.

## 2026-11-21 · feat(theater): optional LLM commander and after-action narrative

- **Changed:**
  - New port `CommanderAdvisor` (`domain/ports.py`). `CommanderAgent.decide(..., advisor=...)`: after the rules filter and resolve conflicts, an advisor may pick among the eligible validated COAs within attention; others get `not_selected_by_c2`.
  - `Simulation(advisor=...)` + `RunConfig.llm_commander` / `llm_choices`: picks and Spanish explanations go to the audit log (`llm_choice`) and the recipe; replays reuse them and never call the LLM.
  - New `infrastructure/llm.py`: `ClaudeCommander` and `ClaudeInterpreter` on the Anthropic SDK (`claude-opus-5-5`, effort `low`, JSON schema output, server-side refusal fallback `"default"`), wired by `llm_adapters(settings)` in the API. Optional extra `llm` (`anthropic>=1.0.0`, lock updated).
  - `POST /sim/runs` field `llm_commander`; settings `CASCADASEN_LLM_ENABLED`, `_MODEL`, `_EFFORT`, `_TIMEOUT_S`.
- **Why:** Ricardo chose rules by default plus an optional LLM as C2 that only chooses among validated options.
- **Agents:** `strategy.md` 10 now allows the LLM as C2 (never the adversary, never computing or validating). Without the extra or credentials everything runs as before. Campaigns never pass an advisor. Tests use fake advisors/clients; no test calls the API.
- **Files:** `backend/src/cascadasen/domain/ports.py`, `domain/agents/commander.py`, `domain/theater/cycle.py`, `infrastructure/llm.py`, `infrastructure/settings.py`, `application/run_experiment.py`, `application/simulation_service.py`, `api/simulation_routes.py`, `api/simulation_schemas.py`, `params/narrative_es.yaml`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/unit/test_llm_commander.py`, `backend/README.md`, `docs/strategy.md`, `docs/stack.md`.

## 2026-11-21 · feat(theater): campaigns with random seeds and spread across seeds

- **Changed:** `POST /sim/campaigns` accepts `random_seeds` (1-10): fresh seeds drawn per campaign, returned in `spec.seeds`, the same in every cell. Each row adds `spread` with p10/p50/p90 of mission continuity and recoverability. New API guardrail test: no run, trace, report or campaign payload carries adversary `weights`, `arms`, `probs` or a `ranking`.
- **Why:** With chance in the world, a policy is judged by its distribution over many runs, not by one seed.
- **Agents:** Explicit `seeds` still work and are the way to get stable numbers. `CampaignSpec.random_seeds`.
- **Files:** `backend/src/cascadasen/application/run_campaign.py`, `backend/src/cascadasen/api/simulation_schemas.py`, `backend/src/cascadasen/api/simulation_routes.py`, `backend/tests/integration/test_campaigns_api.py`, `docs/stack.md`.

## 2026-11-21 · feat(theater): field crews with home bases and road travel

- **Changed:**
  - New `domain/theater/crews.py` (`CrewRoster`): crews with a base and position, travel time from area centroids (haversine × road factor / speed + mobilisation, spread from the `field` stream), dispatch of the nearest free crew within `max_eta_cycles`, timed or held tasks.
  - Verification, manual operation and re-arming wait for the crew (`ExecutionState.arrivals`, note `crew_arrived`); repairs start at arrival. Field reports arrive with the crew.
  - Logistics vetoes crew actions whose nearest free crew is too far (`log_crew_too_far`); `AgentView.crew_eta` gives it the nearest free crew per area. Executed records carry `crew` and `arrival`; snapshots carry `crews`.
  - `theater.yaml`: new `crews` section; `field_crews` 6 → 9.
- **Why:** Ricardo wants defenders that repair anywhere in the country with real distances.
- **Agents:** The flagship validation now asserts that C keeps the most continuity; B no longer beats A once crews are on the map (finding recorded in `strategy.md` 6). New verdict codes `no_crew_in_range`, `action_failed`, `failed` have Spanish text in `narrative_es.yaml`. `request_external_support` does not add crews yet.
- **Files:** `backend/src/cascadasen/domain/theater/crews.py`, `execution.py`, `cycle.py`, `config.py`, `params/theater.yaml`, `params/narrative_es.yaml`, `backend/src/cascadasen/domain/agents/logistics.py`, `base.py`, `backend/tests/unit/test_crews.py`, `backend/tests/validation/test_flagship.py`, `docs/strategy.md`, `docs/stack.md`.

## 2026-11-21 · feat(theater): chance in the world on independent seeded streams

- **Changed:**
  - New `domain/theater/stochastic.py` (`Chance`) with streams `physics`, `external`, `ops`, `field`: sampled event sizes (Beta/lognormal around catalog defaults), defence functions that fail to act per transient (`misoperated_defenses` in `last_transient`), unplanned zone-level E1/E2 events (source `external`), first-attempt action failures (`action_failed`), repair-time and restoration-speed spread, field crews missing a digital issue.
  - `theater.yaml` gains a `stochastic` section; `TheaterConfig.stochastic`.
  - `RunConfig.stochastic` / `POST /sim/runs` `stochastic` (default true) switches it off.
- **Why:** Ricardo wants runs to behave like real life, not a script, while keeping replay and fair comparisons.
- **Agents:** `Executor(..., chance=None)` keeps the old deterministic behaviour (used when `stochastic` is false). Explicit params from scenarios or users are never sampled. A failed action spends attention only. `restore_element` crews are now released by the executor when the repair ends, not at a fixed cycle. Numbers quoted for the flagship in older entries were computed without chance; use `stochastic: false` to compare.
- **Files:** `backend/src/cascadasen/domain/theater/stochastic.py`, `execution.py`, `cycle.py`, `config.py`, `params/theater.yaml`, `backend/src/cascadasen/api/simulation_schemas.py`, `backend/src/cascadasen/application/run_experiment.py`, `backend/tests/unit/test_theater_stochastic.py`, `docs/strategy.md`, `docs/cyber.md`.

## 2026-11-21 · feat(theater): random seed by default, recorded in the recipe

- **Changed:** `RunConfig.seed` and `POST /sim/runs` `seed` are optional. Without one, the run draws a fresh seed (`theater/rng.new_seed`), stores it in its config, the `run_created` audit entry and the summary. Named streams moved to `domain/theater/rng.py` (`rng_for(seed, name)`).
- **Why:** Ricardo wants every run to differ like real life while keeping replay and fair policy comparison (same seed, same luck).
- **Agents:** Pass an explicit `seed` for stable fixtures, tests and comparisons (`cascadasen-sim-fixtures --seed 7` still does). `replay` keeps the original seed. New stochastic sources must draw from their own `rng_for(seed, "<name>")` stream, never from the defence stream.
- **Files:** `backend/src/cascadasen/domain/theater/rng.py`, `backend/src/cascadasen/domain/theater/cycle.py`, `backend/src/cascadasen/api/simulation_schemas.py`, `backend/src/cascadasen/application/run_experiment.py`, `backend/tests/unit/test_theater.py`, `docs/stack.md`.

## 2026-11-21 · fix(theater): adversary arms for defence events and recovery reward

- **Changed:**
  - The adversary builds its EXP3 arms per target kind: area events over the 13 areas, zone events over zones, C4 over defence functions (`pdce_zn`, `edac:<zone>`, ...). Before, `complicate_recovery` produced `(C4, A0x)` arms and every `degraded_recovery` run crashed with `UnknownEventTargetError`.
  - `Simulation._admissible` resolves each adversary event before applying it; anything that is not an area, zone or defence function is dropped and logged as `adversary_event_rejected`.
  - The `complicate_recovery` reward no longer uses lost load share: it pays for delayed recovery (effect persisted, area still dark).
- **Why:** Bug found while planning the stochastic theatre; the reward change keeps `cyber.md` 8 item 7 (objectives target decision quality, not damage).
- **Agents:** `AdversaryAgent(targets={"area": [...], "zone": [...], "defense": [...]}, ...)` replaces `areas=`. `Pending.area` is now `Pending.target`. Regression test `test_adversary_with_defence_events_runs_and_stays_abstract`.
- **Files:** `backend/src/cascadasen/domain/agents/adversary.py`, `backend/src/cascadasen/domain/theater/cycle.py`, `backend/tests/unit/test_theater.py`.

## 2026-11-21 · feat(theater): Spanish narration, after-action review and offline fixtures

- **Changed:**
  - New `domain/theater/params/narrative_es.yaml` with Spanish templates for every `text_key`, `rationale_key`, label, question and reason code, served at `GET /api/v1/sim/narrative`.
  - New `domain/theater/narrative.py` with Spanish number format and a `TemplateInterpreter`, the default for the new `Interpreter` port in `domain/ports.py`. It backs `GET /sim/runs/{id}/after_action`.
  - New CLI `cascadasen-sim-fixtures` that writes network, catalog, narration, 25F timelines, flagship runs per policy and a campaign.
  - Recoverability is now measured from the worst-continuity cycle, not from the first effect.
  - `backend/README.md` gains the V1-V10 status table.
- **Why:** The frontend renders Spanish narration from keys (stack.md 9). This gives it one source of truth plus a ready after-action review and offline fixtures (stack.md 9: keep the demo working offline).
- **Agents:**
  - Every catalog event, action, objective, policy and question must have a template (tested).
  - The LLM interpreter is not built. It would implement `Interpreter`; adding it needs the `anthropic` dependency and an API key decision from the team, and it would explain, never decide.
  - Fixtures go to `data/processed/sim/` (about 1.6 MB, regenerate rather than edit).
- **Files:** `backend/src/cascadasen/domain/theater/narrative.py`, `backend/src/cascadasen/domain/theater/params/narrative_es.yaml`, `backend/src/cascadasen/domain/theater/evaluator.py`, `backend/src/cascadasen/domain/ports.py`, `backend/src/cascadasen/application/run_experiment.py`, `backend/src/cascadasen/api/simulation_routes.py`, `backend/src/cascadasen/sim_fixtures.py`, `backend/pyproject.toml`, `backend/tests/*`, `backend/README.md`, `docs/stack.md`, `docs/strategy.md`.

## 2026-11-21 · feat(theater): campaigns with fragility and adaptation indices

- **Changed:**
  - New `application/run_campaign.py` and endpoints `POST/GET /api/v1/sim/campaigns`.
    - Mode I (diagnostic): continuity per area in geographic order.
    - Mode II (adversarial): policies × uncertainty × static/adaptive adversary, with the Decisional Fragility Index (paired uncertainty-0 runs added automatically) and the Adaptation Index.
    - Mode III (capability): deltas against the baseline variant. Capped at 240 runs.
  - Perfect information (uncertainty 0) now also reports the true supervision losses as alarms.
  - The digital engine was split into an `_Observer` with a fixed call order.
- **Why:** Phase 4 of the plan: compare policies under equivalent conditions and measure how they degrade with uncertainty and against an adaptive adversary.
- **Agents:**
  - A negative fragility index means better information made that policy worse. It happens with the preventive policy against the adaptive adversary, and it is documented as a finding in `strategy.md` 8.
  - Flagship campaign, 3 seeds × levels {0, 1, 2}: 54 runs in ~8 s.
  - `docs/stack.md` 7.1 documents the campaign body.
- **Files:** `backend/src/cascadasen/application/run_campaign.py`, `backend/src/cascadasen/application/simulation_service.py`, `backend/src/cascadasen/api/simulation_*.py`, `backend/src/cascadasen/domain/theater/digital.py`, `backend/tests/integration/test_campaigns_api.py`, `docs/strategy.md`, `docs/stack.md`.

## 2026-11-21 · feat(theater): strategic cycle, agents and runs API

- **Changed:**
  - New `domain/theater/` with real vs observed state and a digital engine (missing, stale or unreliable supervision, false alarms, perfect information at uncertainty 0).
  - Abstract events (C1-C5, D1-D6, E1-E2) and twelve defensive actions.
  - A resource ledger with attention saturation, a deterministic validator (it reads the real state; agents only learn the observable reason) and an execution engine with effect lifecycles and operational restoration.
  - A hash-chained audit log, an evaluator (continuity, awareness, response capacity, resistance, reserve, recoverability, coordination, wrong decisions, Freedom of Action Index) and the six-step cycle.
  - New `domain/agents/`: C2, ISR (Bayesian cause belief), Operations, Stabilisation, Logistics, a read-only Auditor, and the Adversary (EXP3 over the abstract catalog, or the template plan when static).
  - New `application/run_experiment.py` and endpoints `/api/v1/sim/catalog`, `/sim/runs`, `/runs/{id}`, `/events`, `/step`, `/replay`, `/trace`, `/report`.
  - Six experiment templates, including `flagship_observability`, whose 900 MW shock hits while Santiago is blind.
- **Why:** The strategic experimentation layer of `docs/strategy.md`, and the API the frontend uses to select a node, trigger an event and compare policies.
- **Agents:**
  - Agent views never carry `RealState`/`GridState` (tested).
  - An unchanged replay reproduces the trace hash, and the adversary's weights are never exported (only its event-type mix).
  - Event targets accept area, corridor, zone, defence or real `SE…`/`L…` ids. Unknown target or template returns 404, invalid input 422, and an inject into a finished run 409.
  - Flagship (static adversary, seed 7):
    - A, reactive: continuity 0.966.
    - B, preventive: 0.984, but 39 unnecessary actions.
    - C, adaptive: 0.978, with the fewest resources spent and the best response capacity.
  - Every number in `theater.yaml`/`templates.yaml` is a declared design assumption.
- **Files:** `backend/src/cascadasen/domain/theater/*`, `backend/src/cascadasen/domain/agents/*`, `backend/src/cascadasen/application/run_experiment.py`, `backend/src/cascadasen/api/simulation_*.py`, `backend/tests/*`, `backend/README.md`.

## 2026-11-21 · feat(sim): physical engine on the reduced SEN and POST /api/v1/simulate

- **Changed:**
  - New `backend/src/cascadasen/domain/simulation/`: 13 operating areas built from the snapshot. Corridors are split by voltage and keep their parts, so a substation outage removes only its own lines, load and generation.
  - Engine modules: DC power flow, weak-link cascade (>120 %, north defence scheme at 0.23 s, otherwise 1.566 s) and island swing-equation frequency (EDAC steps, extreme gradient shedding, primary reserve, batteries, over-frequency curtailment). Kinetic energy is tracked as state.
  - Outputs: consequence card (L0-L3, people, unserved MWh, cost at 8.79 US$/kWh) and the `timeline.json` builder.
  - API: `POST /api/v1/simulate` (stack.md 7 validation, 422 with valid values, 503 on timeout) and `GET /api/v1/sim/network`.
- **Why:** The strategic layer needs a physics core, and the frontend needs "click a node → see the cascade".
- **Agents:**
  - Every number in `params/*.yaml` carries a source or `is_assumption`; the loader rejects bare numbers.
  - Calibrated values declare their case: the A06-A07/220 reactance (V1), D = 2.0 %/Hz and the reserve time constant of 1 s (V3a), the EDAC step shares (V3a, V3b, V7, V8), the over-frequency curtailment (V5) and the 25F ramp timing (V4).
  - Published EDAC tables ([4] 3-10, [14] Table 1) are still not transcribed. Replace the placeholders when they are.
  - `tests/validation/test_engine_cases.py` passes V1-V5, V7, V8 and V10. V6 and V9 are skipped (reference data missing).
  - `elements_out` accepts corridor, area, `SE…` or `L…`/`T…` ids.
- **Files:** `backend/src/cascadasen/domain/simulation/*`, `backend/src/cascadasen/application/simulate.py`, `backend/src/cascadasen/application/simulation_service.py`, `backend/src/cascadasen/api/simulation_*.py`, `backend/src/cascadasen/api/app.py`, `backend/tests/*`, `backend/README.md`.

## 2026-11-21 · docs(strategy): add strategic experimentation layer and its API contract

- **Changed:** New `docs/strategy.md` covers:
  - the thesis: losing the capacity to understand and coordinate is the main risk;
  - five interacting systems and 13 operating areas reduced from the real SEN;
  - real, observed and estimated state, and two clocks;
  - six defensive agents and an adaptive adversary;
  - the strategic cycle, deterministic validator and hash-chained audit;
  - policies A/B/C, modes I-III, indicators and three experimental indices, and the flagship experiment.

  `cyber.md` section 8 gains item 7 (adaptive adversary rules) and a pointer to `strategy.md`. `stack.md` section 7 now documents `/api/v1/simulate` and the new section 7.1 (`/api/v1/sim/*`). `plan.md` section 9 item 4 records the proposed 13-area node list.
- **Why:** Ricardo reframed CascadaSEN: it simulates whether a utility keeps its mission when it loses the capacity to understand its own state, not attacks. The task is backend only; another teammate builds the frontend against this API.
- **Agents:** Read `strategy.md` after `cyber.md`. The adversary acts only through abstract events at area or function level, and no output ranks elements or areas. The LLM never decides or plays the adversary. Primary user: utility operations and continuity teams, with Mode II (adaptive adversary) first. The framing, item 7 and the node list are pending team confirmation. The implementation lands on branch `feat/strategic-sim-api`.
- **Files:** `docs/strategy.md`, `docs/cyber.md`, `docs/stack.md`, `docs/plan.md`.
## 2026-11-21 · feat(infra): Mapbox token in the web image and deploy-on-main workflow
- **Changed:** `web.Dockerfile` takes the build argument `VITE_MAPBOX_TOKEN`; `deploy.sh` passes it (public `pk.*` default, overridable). New `deploy.sh deploy` command (no plan step). New `.github/workflows/deploy.yml` runs it on every push to `main` through GitHub OIDC.
- **Why:** The deployed map showed the offline fallback because Vite inlines the token at build time. The team wants every commit on main deployed.
- **Agents:** The workflow needs the repository variable `AWS_DEPLOY_ROLE_ARN` and an IAM role plus OIDC provider created by hand; trust policy in `docs/infrastructure.md`. Until then it fails at the credentials step.
- **Files:** `infrastructure/docker/web.Dockerfile`, `infrastructure/deploy.sh`, `.github/workflows/deploy.yml`, `docs/infrastructure.md`.
## 2026-11-21 · feat(web): mapa 3 interface following the Paper design (#28)

- **Changed:** New layout (`.shell` in `styles.css`): a collapsible rail on the left (Sub50, Mapa, Supuestos; the collapsed state is saved in localStorage), a floating panel with the tabs Red, Simulación, Leyenda and Supuestos (the last two used to sit at the bottom of the old right panel), a timeline card at the bottom of the panel (play, scrubber, stage and seconds), the case selector as a pill at the top center of the map, and the 2D/3D toggle plus zoom buttons at the top right. The camera now leaves room on the left, and the Mapbox logo moved to the bottom right. Neutral charcoal colors instead of navy.
- **Why:** The team asked for the full interface of the Paper mockup, with Red and Simulación within reach and the legend and assumptions as tabs.
- **Agents:** Mapa 3 only; the deprecated mapas 1 and 2 keep the old `.layout` and `.panels`. `BaseMap` has a new `zoomBy()`. The camera clearance (`PANEL_CLEARANCE_PX`, 640) is fixed: collapsing the rail does not re-center the map. Not built: rail items Escenarios, Validación, Datos y fuentes, Metodología and Ayuda; tabs Qué lo habría evitado and Validación; the date pill; the "Color de líneas: Tensión" legend and mode; scale bar and layers button; Hz and speed in the timeline.
- **Files:** `web/src/cascade/CascadeApp.tsx`, `web/src/cascade/Legend.tsx`, `web/src/map/baseMap.ts`, `web/src/styles.css`.

## 2026-11-21 · feat(web): Red panel with network summary and node detail (#26)

- **Changed:** The right panel of mapa 3 has two tabs, Red and Simulación (the previous results block). Red shows the Paper design: km of lines (34.578), substations (1.220), installed MW (38.203) and km by voltage band, computed in the browser from `data/processed/geo/{lines,substations,plants}.geojson` (`web/src/cascade/networkSummary.ts`; the numbers match the mockup exactly). Clicking a substation (3D bar, 2D disc or node dot) opens its detail in Red: kV, zone, generation, demand, people, and its connected lines with their loading at the current stage; clicking one of those lines cuts it. A cut line also gets a detail card (capacity, flow, loading). Cutting a line switches to Simulación.
- **Why:** The design has a Red tab; the team asked to visualise each node or line with the data we have.
- **Agents:** Clicking a line on the map still cuts it (not changed). Node data is the reduced network (188 buses); the summary is the full IDE data (1.220 substations), so the two counts differ on purpose. `people` has the known defect (substations with load and 0 people, for example S/E Mauro). Not built: tabs Qué lo habría evitado and Validación, the nav rail, inertia or sync MW per node (not in the cache), per-plant detail.
- **Files:** `web/src/cascade/NetworkPanel.tsx`, `networkSummary.ts` (+ test), `CascadeApp.tsx`, `web/src/styles.css`.

## 2026-11-21 · feat(web): seven more icons for the 2D view (#24)

- **Changed:** Added `plant-hydro`, `plant-gas`, `plant-geothermal`, `plant-biomass`, `grid-tower`, `grid-breaker` and `grid-transformer` (512 px PNG) to the icon folder, and the matching kinds to `IconKind` in `web/src/cascade/icons.ts`. Now 12 icons. All icons live in `web/src/assets/icons/` (moved from `web/public/icons/`, where #23 put the first five) and are imported with `?url` in `icons.ts`, so Vite bundles and hashes them.
- **Why:** The 2D view needs an icon per generation carrier in the data and per grid element in `design.md`.
- **Agents:** Still no icon is drawn: nothing passes `icons` to the View yet. `plant-biomass` is an ASSUMPTION (the image is a plant with a sprout and wind, named `green-factory` by its source). Still missing: diesel, CSP (solar thermal), substation, pole, gantry. `grid-tower.png` is dark gray; the others are black. `mask: true` tints all of them, so the color of the file does not matter.
- **Files:** `web/src/assets/icons/*`, `web/src/cascade/icons.ts`.

## 2026-11-21 · feat(web): 2D view = same map from above, with flat symbols (#22)

- **Changed:** 2D keeps the same Mapbox Standard (night) basemap as 3D and only looks straight down: camera pitch 0 and rotation disabled. The 3D demand bars are replaced by flat discs whose radius grows with the square root of MW (layer id `load-2d`). New 2D-only icon layer: `IconPoint` and `iconLayers()` in `web/src/cascade/icons.ts`, sized in meters on the ground (clamped to 12 to 40 pixels) so icons scale with the zoom. Image files in `web/src/assets/icons/` (`plant-coal`, `plant-wind`, `plant-solar`, `storage-battery`, `power-bolt`; 512 px PNG, black outline on transparent, tinted at draw time with `mask: true`). The legend text changes with the mode.
- **Why:** A different flat basemap (dark-v11) looked worse than the main map. The team chose the same 3D scene seen from above with 2D symbols, so icons can be added without 3D polygons.
- **Agents:** To add icons, build `IconPoint[]` and pass it as `icons` in the `View` given to `buildCascadeLayers` (`CascadeApp.tsx`, `_animate`). Nothing passes it yet, so no icon draws. Plant icons need per-plant data that the cache does not have (`node_index.json` `plants[]` has it). The Standard style still draws 3D buildings and terrain when zoomed in, even in 2D. The offline map (no token) only gets the camera lock. Branched from `feature/21-cities-metadata` (#21); this PR includes that commit until #21 merges.
- **Files:** `web/src/map/baseMap.ts`, `web/src/cascade/layers.ts`, `web/src/cascade/icons.ts`, `web/src/cascade/Legend.tsx`, `web/src/cascade/CascadeApp.tsx`.

## 2026-11-21 · fix(web): city labels become metadata, not drawn (#20)

- **Changed:** The city labels of #19 are no longer drawn. The list moved to `web/src/cascade/cities.ts` (`CITIES`) as data only.
- **Why:** Mapbox already labels these cities, so each name showed twice.
- **Agents:** Nothing imports `CITIES` yet. Use it for search, camera jumps or a breadcrumb. The "city labels" entry below is superseded: those labels are gone from the screen.
- **Files:** `web/src/cascade/layers.ts`, `web/src/cascade/cities.ts`, `CHANGELOG.md`.

## 2026-11-21 · feat(web): city labels in mapa 3 (#18)

- **Changed:** Six reference cities (Arica, Antofagasta, Calama, Santiago, Concepción, Puerto Montt) drawn as a cream dot plus a text label, in deck.gl (`CITIES` in `web/src/cascade/layers.ts`), on top of the grid layers.
- **Why:** The Paper design (`2d.css`) has these labels. It placed them with fixed pixels on a 1440x900 artboard; real coordinates keep them in place when the map zooms or moves.
- **Agents:** The labels are not pickable. Mapbox draws its own city names too, so some appear twice at some zooms. Font is Geist if installed, else system-ui; Geist is not bundled. Branched from `feature/toggle-2d` (#17), so this PR includes that commit until #17 merges.
- **Files:** `web/src/cascade/layers.ts`, `CHANGELOG.md`.

## 2026-11-21 · feat(web): 2D / 3D toggle in mapa 3 (#16)

- **Changed:** A 2D / 3D button at the top of the map (left of the panel). 3D is the previous view: camera pitch 45 and rectangular demand bars. 2D sets pitch 0 and draws demand as flat discs (radius grows with the square root of MW). `?vista=2d` opens in 2D. `BaseMap` has a new `setMode()` for both the Mapbox and the offline map.
- **Why:** The new interface (Paper, design.md) wants the same map in 2D and 3D. This is the toggle only; the nav rail, tabs, city labels and the new colours are not built.
- **Agents:** The 2D demand layer has its own id (`load-2d`). Reusing the id `load` for a different layer class makes deck.gl throw an accessor error. In 2D the discs replace the bars, so there is no height encoding.
- **Files:** `web/src/map/baseMap.ts`, `web/src/cascade/layers.ts`, `web/src/cascade/CascadeApp.tsx`, `web/src/styles.css`.

## 2026-11-21 · feat(web): mapa 3 is the main map; mapas 1 and 2 deprecated (#14)

- **Changed:** `/` and `?mapa=3` open mapa 3 (the cascade viewer). `?mapa=1` (offline deck.gl map) and `?mapa=2` (Mapbox basemap) still work but log a deprecation warning. No code was deleted.
- **Why:** The team chose mapa 3 as the product map. It is the only one with the engine, the legend and the cascade replay.
- **Agents:** Build new UI on `web/src/cascade/`, not on `web/src/map/chileMap.ts` or `mapboxMap.ts`. `docs/mapa3.md` and `docs/minimum-dataset.md` (merged in #12 without a changelog entry) describe the engine, the actors and the minimum dataset. The cache in `web/public/cache/` must be generated (`cascadasen-cache`) or the root page shows an error. Older docs that call `/` "the offline map" (`stack.md`, `docker.md`, `datasets.md`) are out of date on that point.
- **Files:** `web/src/main.tsx`, `web/README.md`, `docs/mapa3.md`, `CHANGELOG.md`.

## 2026-11-21 · chore(project): enlarge Sub50 logo wordmark

- **Changed:** `project-logo.png` is replaced with a version of the same logo (option 01) where the wordmark fills more of the 1000 x 1000 square. 40 KB PNG. `docs/design.md` section 6 updated.
- **Why:** The previous file had a lot of empty margin, so the logo looked small at the README's 200 px.
- **Agents:** Same design as before, only the scale changed. A small-size version is still open.
- **Files:** `project-logo.png`, `docs/design.md`.

## 2026-11-21 · chore(project): align oneliner and project page with the description

- **Changed:** `project-oneliner-spanish` in `platanus-hack-project.jsonc` now condenses `project-description-spanish` into one line: the agent first simulation plus its purpose (finding the most fragile points). `project-description.md` reuses the description's wording ("agent first", "en vivo la infraestructura crítica", "con datos públicos", "conectarse a nuestra API") and keeps its headings and bullets.
- **Why:** The three submission texts said the same thing with slightly different wording.
- **Agents:** `project-description-spanish` is the source text. Change the oneliner and `project-description.md` along with it.
- **Files:** `platanus-hack-project.jsonc`, `project-description.md`.

## 2026-11-21 · chore(project): set Sub50 deploy URL

- **Changed:** `deploy-url` in `platanus-hack-project.jsonc` is now `https://sub50.cl`.
- **Why:** The hackathon submission needs the public URL of the running project.
- **Agents:** All Platanus metadata fields are now filled (`plan.md` section 8). On 2026-11-21 the domain did not resolve yet (no DNS record); check that it serves the app before the submission deadline.
- **Files:** `platanus-hack-project.jsonc`.

## 2026-11-21 · chore(project): add Sub50 logo

- **Changed:** `project-logo.png` replaces the Platanus template logo with the Sub50 logo (option 01, Subscript: "sub" with a subscript "5" and a power-button "0", black on white, 1000 x 1000 PNG, 36 KB). `docs/design.md` sections 1, 6 and 7 record the pick.
- **Why:** The hackathon submission needs a 1000 x 1000 PNG logo under 500 KB.
- **Agents:** The logo is chosen, so do not reopen the logo pick. A small-size version without fine detail is still open. The README embeds the logo at 200 px.
- **Files:** `project-logo.png`, `docs/design.md`.

## 2026-11-21 · chore(project): set Sub50 description in project metadata

- **Changed:** `project-description-spanish` in `platanus-hack-project.jsonc` now holds the final team description (one paragraph that opens with the agent-first framing, then the map, blackout propagation and agent API). `project-name` stays "Sub50".
- **Why:** The hackathon submission reads name and description from this file.
- **Agents:** Do not rewrite the description without the team's approval. `deploy-url` is still `<FILL THIS>`. `project-oneliner-spanish` and `project-description.md` were not changed.
- **Files:** `platanus-hack-project.jsonc`.

## 2026-11-21 · docs: sync docs with the Sub50 name, design sessions and merged work

- **Changed:** New `docs/design.md`: Paper file and pages, Electricity Maps style, voltage and technology palette, 5 zoom levels, data behind the mockups, logo options. Product name Sub50 in titles and summaries (`idea.md`, `AGENTS.md`, `cyber.md`, both READMEs, session hook). `stack.md` now matches the repo (status, Mapbox option, engine base case, real layout, frontend section defers to `design.md`). `plan.md` repo state, submission checklist and open decisions 11-13. `datasets.md` adds the operating points and DC-OPF scripts and sources [40] Mapbox and [41] OpenStreetMap. Backfilled changelog entries for #2, #6, #7, #10 and the Sub50 project-page commit.
- **Why:** The design sessions of 2026-11-21 and five merges changed the product name, the visual direction and the repo state without updating the docs.
- **Agents:** Read order now includes `design.md` after `stack.md` for UI work; it overrides `stack.md` section 5 on visuals. Keep `cascadasen` as the package and command name. Open decision 11 in `plan.md` section 9: the attacker/defender agent framing in `project-description.md` conflicts with `cyber.md` section 8; keep following `cyber.md` until the team decides. `docs/tasks.md` was not touched.
- **Files:** `docs/design.md`, `docs/idea.md`, `docs/stack.md`, `docs/plan.md`, `docs/datasets.md`, `docs/cyber.md`, `AGENTS.md`, `web/README.md`, `backend/README.md`, `.claude/hooks/session_context.sh`, `CHANGELOG.md`.

## 2026-11-21 · feat: node popup, PyPSA-CL demand and a secure DC-OPF base case (cdc2ba0, #10; entry backfilled)

- **Changed:** `data/scripts/build_node_index.py` writes `node_index.json`, read by a click popup in `web/` (`src/map/nodeDetail.ts`) with everything known about a node. `build_operating_points.py` writes demand per bus from PyPSA-CL and merit-order dispatch for 4 operating points. `build_baseline_opf.py` writes a DC-OPF base case per point with no branch above s_nom and an inertia floor.
- **Why:** An overload cascade needs a realistic, secure starting point: how much each bus consumes and generates without overloaded lines.
- **Agents:** Dispatch and demand are simulated from PyPSA-CL inputs, not measured; show them as such. N-1 is not enforced. PyPSA-CL storage units are model candidates, not real batteries. Details in `docs/datasets.md` section 0.
- **Files:** `data/scripts/`, `data/processed/{node_index,operating_points,baseline_opf}.json`, `web/src/map/`.

## 2026-11-21 · feat(infra): attach ACM certificate and Route 53 alias to CloudFront for sub50.cl
- **Changed:** `domain_name` (default `sub50.cl`) drives the zone, the ACM certificate and the CloudFront alias. CloudFront uses the validated certificate (SNI, TLS 1.2 minimum). Apex `A` and `AAAA` alias records point to the distribution. New output `site_url`. The variable `cloudfront_certificate_arn` is removed.
- **Why:** Serve the app on `https://sub50.cl` through CloudFront.
- **Agents:** `aws_acm_certificate_validation` needs `sub50.cl` delegated to the Route 53 name servers (done by the user). Apply with `infrastructure/deploy.sh apply`, which sets `image_tag`. Origin HTTPS stays off; it needs an `alb.sub50.cl` record first (see backlog in `docs/infrastructure.md`).
- **Files:** `infrastructure/*.tf`, `infrastructure/terraform.tfvars.example`, `docs/infrastructure.md`.
## 2026-11-21 · docs(infra): marker line for second deploy

- **Changed:** One marker line in `docs/infrastructure.md`.
- **Why:** New commit gives a new image tag, so the second deploy proves the blue/green swap.
- **Agents:** Previous deploy: task definition `cascadasen:2`, tag `aade205`.
- **Files:** `docs/infrastructure.md`.
## 2026-11-21 · feat(infra): add ACM certificate for sub50.cl (not applied)
- **Changed:** `infrastructure/acm.tf` adds `aws_acm_certificate` (`sub50.cl` + `*.sub50.cl`, DNS), the validation records in the Route 53 zone and `aws_acm_certificate_validation`. Output `acm_certificate_arn`. Docs updated.
- **Why:** A certificate is needed for CloudFront and the ALB HTTPS listener before the domain goes live.
- **Agents:** Plan: 4 to add. Not applied; needs user approval. Apply only works once the registrar delegates `sub50.cl` to the zone's name servers, else validation waits and times out. The stack is deployed: CloudFront `https://d2bc0ohphbh56u.cloudfront.net`, image tag `aade205`, task definition `cascadasen:2`. Not attached to CloudFront yet.
- **Files:** `infrastructure/acm.tf`, `infrastructure/outputs.tf`, `docs/infrastructure.md`.
## 2026-11-21 · fix(infra): build images with buildx as Docker-format gzip layers
- **Changed:** `push_image` in `deploy.sh` uses `docker buildx build --provenance=false --sbom=false --output type=image,push=true,compression=gzip,force-compression=true,oci-mediatypes=false`.
- **Why:** Fargate failed with `CannotPullContainerError: wrong diff id` on images pushed with plain `docker build` + `docker push` from Colima (containerd image store, OCI manifest).
- **Agents:** `docker-buildx` is required (`brew install docker-buildx`, plugin linked in `~/.docker/cli-plugins`). ECR tag `probe1` in `cascadasen/backend` is a test push; ignore it. Images pushed under the old tag format are not usable.
- **Files:** `infrastructure/deploy.sh`.
## 2026-11-21 · fix(infra): auto-approve the targeted ECR apply in deploy.sh
- **Changed:** The ECR-only `terraform apply -target` in `deploy.sh apply` now passes `-auto-approve`.
- **Why:** The step prompted for `yes`, so a non-interactive `apply` hung. The user already approved the plan that includes the ECR repos.
- **Agents:** The full apply still uses the saved `tfplan` and needs no prompt. Run `plan` and get approval before `apply`.
- **Files:** `infrastructure/deploy.sh`.
## 2026-11-21 · docs(tasks): add animation, city and adversarial agent tasks

- **Changed:** `docs/tasks.md` gains animations with audio on attacked infrastructure, an affected people counter, city lights, a clickable city component (population, % dependent on electricity, deaths rising with blackout time) and an adversarial agents backlog item (attacker and resilience agents plus APIs, owner Ricardo).
- **Why:** The team refined the task list. The adversarial agents spec is backlog and is not written yet.
- **Agents:** Open questions are listed in each task (animation and sound mapping, death-rate model and its source, attacker objective and limits). The "% dependent on electricity" value needs a source or `is_assumption: true`. No code or contract changed.
- **Files:** `docs/tasks.md`.
## 2026-11-21 · feat(infra): add Route 53 hosted zone for sub50.cl
- **Changed:** `infrastructure/route53.tf` adds `aws_route53_zone.main` (`sub50.cl`). New output `route53_name_servers`. `docs/infrastructure.md` documents the zone and the NS delegation step.
- **Why:** The team will serve the app from sub50.cl; the zone must exist first so its name servers can be delegated at the .cl registrar.
- **Agents:** Zone only: no records, no ACM certificate, no CloudFront alias. The domain is not registered by Terraform. Plan is now 39 to add. `apply` still needs explicit user approval.
- **Files:** `infrastructure/route53.tf`, `infrastructure/outputs.tf`, `docs/infrastructure.md`.
## 2026-11-21 · docs(infra): document the AWS deployment
- **Changed:** `docs/infrastructure.md` covers architecture, sizing, blue/green, `deploy.sh plan|apply`, tag scheme, Route 53 + ACM variables and the backlog. `docs/docker.md` links to it.
- **Why:** AGENTS.md requires docs with each behavior change.
- **Agents:** Backlog items have no issue numbers: `scripts/issue.sh` is missing and the fork has issues disabled. Create them upstream when the team agrees. The two-target-group blue/green setup is validated by Terraform only; the ECS API confirms it at first apply.
- **Files:** `docs/infrastructure.md`, `docs/docker.md`.
## 2026-11-21 · feat(infra): add deploy.sh with plan and apply phases
- **Changed:** `infrastructure/deploy.sh plan` checks the AWS account (402909940511), creates the versioned, encrypted state bucket `cascadasen-tfstate-402909940511` if missing, runs init/fmt/validate/plan and writes `infrastructure/.deploy-tag`. `apply` creates ECR, builds and pushes both images (`linux/amd64`), then applies a fresh plan and prints the CloudFront URL. `terraform.tfvars.example` lists the optional variables.
- **Why:** The user runs deploys with their own credentials; plan and apply are split so the plan is reviewed first.
- **Agents:** Credentials come from the environment, else the keys file (never printed, no `AWS_PROFILE`). Image tag is the short commit, plus `-dirty-<UTC time>` when `backend`, `web`, `data` or `infrastructure/docker` have uncommitted changes. ECR is immutable, so `apply` skips a build when the tag already exists. `apply` aborts if the tree changed since `plan`. Only run `apply` after the user approves the plan.
- **Files:** `infrastructure/deploy.sh`, `infrastructure/terraform.tfvars.example`.
## 2026-11-21 · feat(infra): add Terraform stack for ECS Fargate behind ALB and CloudFront
- **Changed:** `infrastructure/*.tf` defines a VPC with 2 public subnets, an ALB (production listener :80, test listener :8080, 4 target groups), one ECS Fargate service (1 task, 2 vCPU / 4 GB, containers `backend` :8000 and `web` :80) with native ECS blue/green on two `load_balancer` blocks, two immutable ECR repos, CloudWatch logs, and a CloudFront proxy (no cache, redirect to HTTPS). State uses an S3 backend with `use_lockfile`.
- **Why:** POC deployment requested by the team. An ALB cannot hold an Elastic IP, so CloudFront points to the ALB DNS name.
- **Agents:** Variables: `image_tag` (required, set by deploy.sh), `domain_name`, `cloudfront_certificate_arn`, `origin_https`, `alb_certificate_arn` (all optional). ECS rewrites the listener-rule forward actions on each deployment, so those rules use `ignore_changes = [action]`. No Route 53 resources yet. Never run `terraform apply` by hand; `infrastructure/deploy.sh` comes in the next commit.
- **Files:** `infrastructure/*.tf`, `infrastructure/.terraform.lock.hcl`.
## 2026-11-21 · feat(docker): add docker compose stack for backend and web
- **Changed:** `docker-compose.yml` runs `backend` (FastAPI, :8000) and `web` (Vite dev server with npm, :5173). `backend/Dockerfile` installs from `uv.lock`. `web/Dockerfile` uses `npm ci`; compose bind-mounts `./web` and `./data` because the app imports `../data/processed`. Optional `data-build` profile rebuilds `data/processed`. Host ports are configurable with `WEB_PORT` and `BACKEND_PORT`. Root `.gitignore` also ignores `node_modules/`, `dist/`, `.env.local`, `.DS_Store` and `.playwright-mcp/`.
- **Why:** Run and simulate the whole project locally with only Docker installed.
- **Agents:** Start everything with `docker compose up --build`. Details in `docs/docker.md`. The services are independent: the web app does not call the backend. `?mapa=2` needs `web/.env.local` with `VITE_MAPBOX_TOKEN`. Keep `backend/uv.lock` and `web/package-lock.json` current, the images install with `--locked` / `npm ci`.
- **Files:** `docker-compose.yml`, `backend/Dockerfile`, `backend/.dockerignore`, `web/Dockerfile`, `web/.dockerignore`, `docs/docker.md`, `docs/stack.md`, `.gitignore`.

## 2026-11-21 · chore(project): fill Sub50 name, description and project page (c33587e; entry backfilled)

- **Changed:** `platanus-hack-project.jsonc` and `project-description.md` now carry the name Sub50, a Spanish oneliner and description. `deploy-url` is still unfilled.
- **Why:** Platanus submission metadata.
- **Agents:** The product is Sub50. The description frames the project as AI agents attacking and defending the grid through an API, which conflicts with `cyber.md` section 8 (open decision 11 in `plan.md` section 9).
- **Files:** `platanus-hack-project.jsonc`, `project-description.md`.

## 2026-11-21 · docs(cyber): reframe as hackathon resilience scenarios

- **Changed:** `docs/cyber.md` now opens with a context paragraph: hackathon simulation-track project, educational and preventive, grid-level effects only. Attacker-centred wording is replaced by resilience and continuity-planning terms. The "attack vs random failure" table is now "what a resilience study must represent beyond classic N-1". Classes renamed: C4 "Defence not acting", C5 "Loss of remote dispatch", C6 "Combined stress test".
- **Why:** The old wording read like attack planning even though the content was already consequence-only. The purpose should be explicit.
- **Agents:** Data, sources, section numbers and IDs (C1-C6, Q1-Q6, L0-L3, V7/V10) and contract field names are unchanged, so cross-references still hold. Write about this scenario family as "cyber incident" or "disturbance" effects, never from an attacker's point of view. `idea.md` and `AGENTS.md` still say "consequences of cyberattacks" in a few lines; align them if touched.
- **Files:** `docs/cyber.md`.

## 2026-11-21 · chore: ignore all .env files except .env.example (b41f003, #7; entry backfilled)

- **Changed:** `.gitignore` ignores every `.env*` file except `.env.example`.
- **Why:** Keep tokens such as the Mapbox key out of the repo.
- **Agents:** Put secrets only in git-ignored env files. The web app reads `web/.env.local`.
- **Files:** `.gitignore`.

## 2026-11-21 · feat(web): mapa2, Mapbox vector basemap with the grid on top (a920317, #6; entry backfilled)

- **Changed:** `?mapa=2` mounts a Mapbox basemap (Standard, night) with the deck.gl grid layers on top through `MapboxOverlay`. The token comes from `VITE_MAPBOX_TOKEN` in `web/.env.local`; `web/.env.example` added. Without a token it falls back to the offline map.
- **Why:** Street-level context under the grid.
- **Agents:** This reverses the "no tile server" choice for this view only; the default map stays offline. Restrict the token by URL in the Mapbox account, since Vite bundles it.
- **Files:** `web/src/map/mapboxMap.ts`, `web/src/main.tsx`, `web/src/map/layers.ts`, `web/.env.example`, `web/README.md`.

## 2026-11-21 · feat(web): deck.gl map of Chile with the SEN grid in 3D (ce82cf2, #2; entry backfilled)

- **Changed:** New Vite + React + TypeScript app in `web/`: full-screen deck.gl map, lines by voltage, main-grid substations and generation columns per node from `data/processed/geo/`, a floating right legend panel, and a light Chile outline built by `data/scripts/build_chile_outline.sh`. Vitest covers plant-per-node aggregation.
- **Why:** First frontend MVP (`docs/stack.md` section 0): frontend only, no physics.
- **Agents:** Run with `cd web && npm install && npm run dev`. Before committing run `npx tsc --noEmit`, `npm test` and `npm run build`. Details in `web/README.md`.
- **Files:** `web/`, `data/scripts/build_chile_outline.sh`, `data/processed/chile.geojson`.

## 2026-11-21 · docs(tasks): assign owners and add cost, market and DIgSILENT tasks

- **Changed:** `docs/tasks.md` assigns Vale and Ignacio to "New features" and to the count of people affected by blackouts. It adds three tasks: market values (Ignacio, Valentina); estimating the values and costs of the 25F blackout and of the solar plant hack; and studying DIgSILENT.
- **Why:** Team task update.
- **Agents:** `docs/tasks.md` belongs to the team; do not overwrite it. The "solar plant hack" task is the Huatacondo case documented in `docs/cyber.md` section 2. Blackout costs use the CNE failure cost [19] (`docs/stack.md` section 6.1).
- **Files:** `docs/tasks.md`.

## 2026-11-21 · docs: link agent workflow from stack and plan

- **Changed:** The decisions table in `docs/stack.md` now lists the CI lint and the agent tooling, and section 9 points to `AGENTS.md`. Section 10 of `docs/plan.md` starts with `AGENTS.md`, the newest changelog entries and the git hook setup.
- **Why:** So that the docs read order leads to the workflow rules.
- **Agents:** `AGENTS.md` is the single source for workflow rules. `stack.md` only links to it.
- **Files:** `docs/stack.md`, `docs/plan.md`.

## 2026-11-21 · chore(agents): add AGENTS.md, CLAUDE.md and Claude Code hooks

- **Changed:** `AGENTS.md` holds the rules for every agent: read the docs before every plan and change, lint, one changelog entry per commit, conventions, tooling map. `CLAUDE.md` imports it. `.claude/settings.json` adds four hooks: lint the edited file (PostToolUse), block `git commit` without a staged `CHANGELOG.md` (PreToolUse), inject the docs read order and newest entries (SessionStart), and a reminder on each prompt (UserPromptSubmit). `.gitignore` now ignores `.claude/settings.local.json`.
- **Why:** Ricardo asked that agents read the docs before each plan and change, and that every change be linted and logged.
- **Agents:** Read `AGENTS.md` first. Fix what the lint hook reports. When a commit is blocked, write the changelog entry. This overlaps with Alonso's "Agentic setup" task in `docs/tasks.md`; coordinate before changing the tooling.
- **Files:** `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/*`, `.gitignore`.

## 2026-11-21 · ci: add ruff and changelog check workflow

- **Changed:** `.github/workflows/lint.yml` runs `ruff check` and `ruff format --check` on `backend/` with ruff 0.17.6, the version in `uv.lock`. On pull requests it fails when `CHANGELOG.md` did not change.
- **Why:** Enforce lint and the changelog remotely, not only on machines that have the hooks enabled.
- **Agents:** The workflow has not run on GitHub yet. Check its first run.
- **Files:** `.github/workflows/lint.yml`.

## 2026-11-21 · chore(lint): add shared lint script and git pre-commit hook

- **Changed:** `scripts/lint.sh --fix|--check FILE...` runs ruff on Python files and eslint/prettier on `frontend/` files once those tools are installed. It skips every other file. `scripts/hooks/pre-commit` lints the staged files and requires a staged `CHANGELOG.md`. Merge commits are exempt; `SKIP_CHANGELOG=1` covers exceptions.
- **Why:** Every change is linted with the right tool, and hooks, CI and humans share one entry point.
- **Agents:** Run `git config core.hooksPath scripts/hooks` once per clone. The hook checks the working-tree copy of each staged file.
- **Files:** `scripts/lint.sh`, `scripts/hooks/pre-commit`.

## 2026-11-21 · docs(cyber): simulation objective is the consequence of cyberattacks

- **Changed:** New `docs/cyber.md`: the main objective of the simulation is to estimate the consequences of cyberattacks on the SEN, modelling the effect and never the technique. It includes questions Q1-Q6, scenario classes C1-C6, consequence levels L0-L3, validation case V10 (Huatacondo, Aug 2026), dual-use guardrails and data gaps. `idea.md`, `plan.md`, `stack.md` (section 6.1, optional `timeline.json` fields and API fields) and `datasets.md` (sources [34]-[39]) were updated to match.
- **Why:** Requested by Ricardo on 2026-11-21. Public case: the Huatacondo plant (103 MW PV + 98 MW / 312 MWh battery) in Tarapaca, disconnected on 27 Aug 2026 after a cyberattack.
- **Agents:** Read order is now `idea.md` -> `cyber.md` -> `stack.md` -> `datasets.md` -> `plan.md`. The older rule "say failure, not attack" was replaced by "describe events by effect, never by attack technique". The no-minimum-cut rule stays. The team has not confirmed the framing yet (`plan.md` section 9, item 10). Huatacondo facts come from pv magazine (secondary source); the Ukraine figures are not verified.
- **Files:** `docs/cyber.md`, `docs/idea.md`, `docs/plan.md`, `docs/stack.md`, `docs/datasets.md`.

## 2026-11-21 · docs(changelog): add agent-facing changelog backfilled from history

- **Changed:** Added `CHANGELOG.md`. Each entry's heading is the commit subject, followed by Changed, Why, Agents and Files. Earlier commits were backfilled from the git history.
- **Why:** Each commit should leave a short summary that tells the next agent what changed.
- **Agents:** Add one entry at the top with every commit.
- **Files:** `CHANGELOG.md`.

## 2026-11-21 · feat(data): unified SEN grid data API and test map (6bc580a, merged in #1)

- **Changed:** Added the `backend/` package `cascadasen` (ports and adapters). It unifies IDE Energia, CEN Infotecnica, PyPSA-CL `Topology.xlsx` and INE Censo 2024 into one grid graph, runs 18 validation checks on each build, and serves a read-only FastAPI at `/api/v1` plus a deck.gl test map at `/map`. Processed outputs are committed in `data/processed/`.
- **Why:** The team needed one verified data source for the grid before building the map and the engine.
- **Agents:** Commands: `cd backend && uv run cascadasen-build`, `uv run cascadasen-api`, `uv run pytest`. To add a source, write one adapter implementing `GridDataSource` and register it in `infrastructure/container.py`. The raw cache `data/raw/` is git-ignored. Details in `backend/README.md` and `docs/datasets.md` section 0.
- **Files:** `backend/`, `data/processed/`, `docs/datasets.md`.

## 2026-11-21 · docs(stack): revise architecture around frontend-only MVPs (d024d44)

- **Changed:** The first MVPs are frontend only and read hand-written fixtures. Engine, API, precompute, CI and LLM were marked as backlog.
- **Why:** Planning session of 2026-11-21.
- **Agents:** Fixture numbers must carry an "assumption" or "fixture" label. The engine will later write files in the same format as the fixtures.
- **Files:** `docs/stack.md`.

## 2026-11-21 · docs: ideas, tasks and plan (ed87ffa)

- **Changed:** Added `docs/idea.md`, `docs/stack.md`, `docs/datasets.md`, `docs/plan.md` and `docs/tasks.md`.
- **Why:** The team chose the CascadaSEN idea (grid blackout simulator, 25F validation).
- **Agents:** `docs/tasks.md` belongs to the team; do not overwrite it.
- **Files:** `docs/`.

## 2026-11-21 · Platanus template (2c494db..8763198)

- **Changed:** Organiser template: `README.md`, `platanus-hack-project.jsonc`, `project-description.md`, `project-logo.png`.
- **Agents:** The metadata is still `<FILL THIS>` (`plan.md` section 8). The README's banana-emoji line is part of the template; ask the team before touching it.
- **Files:** root template files.
