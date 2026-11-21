# Changelog

Written for agents. Newest entry first. Each commit adds one entry at the top, using the format in `AGENTS.md` section 3. Read the newest entries before planning or changing anything. They record what changed after the docs were written.

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
