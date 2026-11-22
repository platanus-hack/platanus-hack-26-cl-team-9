# Documentation index

Every file in `docs/`, what it is for, when to read it, and whether it still matches the code. Statuses were checked against the code on the commit that last edited this file; where a doc is stale the reason is in the row. When a doc and the code disagree, the code wins and the doc gets fixed in the same change (`AGENTS.md` section 1).

Start with [`../llms.txt`](../llms.txt) (the same map for an LLM), then [`code-map.md`](code-map.md) (the code, module by module) and [`for-reviewers.md`](for-reviewers.md) (claims and where to verify them). `AGENTS.md` gives the order to read before changing anything.

Status legend:
- **current**: every file path the doc cites exists, every API path it names is in the route table of `index/repo-index.json`, and the main claims I spot-checked against the code hold. This is a check, not a proof.
- **partly stale**: has sections that no longer match; the row says which.
- **historical**: kept for the record; do not use it to learn how the code works.

## 1. Every file

| File | What it is | Read it when | Status |
|---|---|---|---|
| [`idea.md`](idea.md) | Product, scope, limits, risks of Sub50 | You need the purpose and the honest limits (sections 1, 5, 8) | **Partly stale.** Sections 2-4 describe a 10-14-node network and UI selectors for defence mode and cause that are not built; the map runs on 188 buses ([`adr/0002`](adr/0002-reduced-188-bus-network.md)). Sections 1, 5 and 6 hold |
| [`cyber.md`](cyber.md) | Main objective (consequences of cyberattacks) and its guardrails | Before any scenario, tool or UI work. Section 8 is the rule: model the effect, never the technique, never search for the worst attack | **Current** for section 8: tests enforce it ([`for-reviewers.md`](for-reviewers.md) claim 9) |
| [`stack.md`](stack.md) | Decisions, simulation model (section 4), data contracts (6), HTTP API (7), conventions (9) | You need the cascade rules, the `timeline.json` contract or the session overlay (6.2) | **Partly stale.** Section 0 is history; 4.1 describes the first 10-14-node design (the 188-bus engine is in [`engine.md`](engine.md)); section 6 is marked draft |
| [`design.md`](design.md) | Visual direction, colours, zoom levels, logo | UI work | **Current** for mapa 3 (Design v5 with the v6 line colours); the older Paper pages are not implemented |
| [`datasets.md`](datasets.md) | Sources, the unified pipeline, provenance rule (section 6), source list (7) | You touch data or need where a number comes from | **Current**, with two stated gaps: appendices A and B name scripts that are not in the repo, and the files of 2.3 live outside it |
| [`plan.md`](plan.md) | Phases, validation cases V1-V10 (section 5), open decisions (section 9) | You need what V1-V10 mean or which decisions are still open | **Partly stale.** Sections 0-4 and 8 are the hackathon plan with hour estimates (historical); sections 5 and 9 are kept up to date |
| [`architecture.md`](architecture.md) | How the system is built: ports, layers, flows, frontend folders | First, for the picture | **Current** (web folders and the sessions route fixed on this commit) |
| [`adr/`](adr/README.md) | Five decision records: two engines, 188 buses, DC flow, sessions by URL capability, layering | You ask "why is it built this way?" | **Current.** [`0003`](adr/0003-dc-power-flow.md) matches the engine; [`0005`](adr/0005-hexagonal-layering.md) matches `tests/unit/test_architecture.py` |
| [`engine.md`](engine.md) | The 188-bus cascade engine: steps, assumptions, results, cost | You change or explain a cut | **Current.** Numbers were re-measured on 2026-11-22 and are pinned by `tests/validation/test_results_so_far.py` |
| [`minimum-dataset.md`](minimum-dataset.md) | Attributes the engine needs and what happens in the code when a line is cut | You modularise the simulator or add a country | **Current** (file names resolve) |
| [`health.md`](health.md) | Grid health index (margin to the limit) and failure cost | You touch `domain/cascade/health.py` or the cost fields | **Current** |
| [`dependency.md`](dependency.md) | Who feeds whom, criticality, heat maps | You touch the heat maps or `tracing.py` / `criticality.py` | **Current** |
| [`stress.md`](stress.md) | Prepared scenarios: batch changes by filters for the MCP and the assistant | You use or change `prepare_scenario` or `/grids/prepare` | **Current** |
| [`grids.md`](grids.md) | Grids as documents: layout, endpoints, publishing | You touch `/grids/*` or `cascadasen-grids` | **Current** |
| [`regional.md`](regional.md) | Other countries' networks: drawn layers, Brazil flow network | You add or change a country layer | **Current** |
| [`network-format.md`](network-format.md) | Data contract to add or upload a network, readiness levels | You prepare a network file | **Current** |
| [`strategy.md`](strategy.md) | The strategic theatre: thesis, states, agents, cycle, indicators, guardrails | You work on runs, agents or indicators | **Current** for the design; the header says it still needs team confirmation |
| [`agents.md`](agents.md) | What the agents know about the physics and how they act | You touch `domain/agents/` or the physical alarms | **Current** after the fix of section 1.3 on this commit: the 188-bus engine no longer returns `voltage_limited`, the theatre branches that read it are dead (pending decision, [`for-reviewers.md`](for-reviewers.md) section 4) |
| [`attack-sim.md`](attack-sim.md) | Documented-incident scenarios (Huatacondo, 25F, ...) over the theatre | You touch `/attacks/catalog`, `domain/theater/incident.py` or the Incidentes view | **Partly stale by its own header.** Sections 3 and 5 describe a first proposal that was not built; the header and 3.1 say what exists. Team decision of section 9 pending |
| [`mapa3.md`](mapa3.md) | The cascade viewer: actors, how to use it, legend, files, session mode | You work on the web app or explain what the map shows | **Current** except section 11: shared sessions are hidden in the web since #101 and the section says what stays live |
| [`sessions-api.md`](sessions-api.md) | Guide for agents and clients of the sessions API | You call or change `/sessions/*` | **Current** (the `?sesion=` sentence fixed on this commit) |
| [`mcp.md`](mcp.md) | The MCP server and its 26 tools | You connect an LLM client or change a tool | **Current** |
| [`assistant.md`](assistant.md) | The in-app assistant: endpoint, loop, limits, web client | You touch `/assistant/*` or `web/src/assistant/` | **Current** after the fixes of "Which session", restore and the tool count on this commit |
| [`openapi.md`](openapi.md) | Conventions of the agent-only OpenAPI spec | You add or change an agent route | **Current** |
| [`openapi/agents.openapi.json`](openapi/agents.openapi.json) | The generated agent spec, versioned | You need the machine-readable contract | **Generated.** `tests/integration/test_agent_openapi.py` fails when it is stale |
| [`docker.md`](docker.md) | Run everything locally with Docker | You run the app | **Current** |
| [`infrastructure.md`](infrastructure.md) | AWS deployment: images, ECS, CloudFront, buckets, the deploy workflow | You deploy or read the hosting | **Current** (the `checks` gate of `deploy.yml` added on this commit). Terraform is in `infrastructure/*.tf` and is not described here line by line |
| [`index/`](index/README.md) | The generated repository index and how to query it | You look for a file, symbol, route, test or doc heading | **Generated.** `tests/integration/test_repo_index.py` fails when it is stale |
| [`code-map.md`](code-map.md) | Module-by-module map of backend and web, data flows, tests per module | You start reading the code | **Current** on its commit; lines move, use the index for current ones |
| [`for-reviewers.md`](for-reviewers.md) | Claims to evidence, commands, limitations, pending product decisions | You review or audit the repo | **Current** on its commit |
| [`pitch_idea.md`](pitch_idea.md) | Empty list of pitch bullets | Never for the code | **Historical** (a placeholder) |
| [`tasks.md`](tasks.md) | The team's own task notes | You are a team member. Agents do not edit it (`AGENTS.md` section 4) | **Team-owned**, not checked |
| [`images/`](images) | Three screenshots of mapa 3 used by [`mapa3.md`](mapa3.md) | Never on their own | **Historical** screenshots of the Design v5 shell |

## 2. Where is X

Backend paths are under `backend/src/cascadasen/`, tests under `backend/tests/`, web under `web/src/`. `path:line` is the definition.

| X | Code | Doc | Tests |
|---|---|---|---|
| Cascade engine (188 buses, the map and the theatre) | `run_cascade_workflow` (`domain/cascade/engine.py:106`), `_cascade` (`domain/cascade/engine.py:238`) | [`engine.md`](engine.md) | `unit/test_cascade.py`, `validation/test_results_so_far.py` |
| 13-area engine (`POST /api/v1/simulate`) | `run_transient` (`domain/simulation/engine.py:398`), `PhysicsSimulator.simulate` (`application/simulate.py:128`) | [`stack.md`](stack.md) section 4 | `unit/test_sim_engine.py`, `validation/test_engine_cases.py` |
| Validation cases V1-V10 | `validation/test_engine_cases.py` (V1 at `test_v1_25f_flow_split` (`validation/test_engine_cases.py:55`), V10 at `test_v10_huatacondo_103_mw_midday` (`validation/test_engine_cases.py:128`)) | [`plan.md`](plan.md) section 5, table in [`../backend/README.md`](../backend/README.md) | the same file; V6 and V9 skip |
| Frequency model | 188 buses: `simulate_island` (`domain/cascade/frequency.py:126`) (EDAC tables: `edac_tables` (`domain/cascade/frequency.py:98`)). 13 areas: `simulate_island` (`domain/simulation/frequency.py:102`) | [`engine.md`](engine.md) item 5, [`stack.md`](stack.md) 4.4 | `unit/test_cascade.py`, `unit/test_sim_engine.py` |
| Parameters and provenance | `check_provenance` (`domain/simulation/params.py:43`); YAML in `domain/cascade/params/`, `domain/simulation/params/`, `domain/theater/params/` | [`datasets.md`](datasets.md) section 6 | `test_cascade_parameters_carry_provenance` (`unit/test_cascade.py:332`) |
| Strategic theatre and its cycle | `Simulation` (`domain/theater/cycle.py:141`), `Simulation._cycle` (`domain/theater/cycle.py:583`) | [`strategy.md`](strategy.md), [`agents.md`](agents.md) | `unit/test_theater.py`, `validation/test_flagship.py` |
| Documented incidents | `incident_catalog` (`domain/theater/incident.py:81`), `start_incident_run` (`api/incident_routes.py:94`) | [`attack-sim.md`](attack-sim.md) | `unit/test_incidents.py` |
| Sessions | `SessionService` (`application/sessions.py:82`), `router` (`api/session_routes.py:68`), web `useSession` (`session/useSession.ts:19`) | [`sessions-api.md`](sessions-api.md), [`adr/0004`](adr/0004-sessions-on-s3-by-url-capability.md), [`mapa3.md`](mapa3.md) section 11 | `unit/test_sessions.py`, `integration/test_sessions_api.py` |
| MCP tools | `Sub50Tools` (`mcp/tools.py:76`), `OPERATIONS` (`mcp/tools.py:20`), server `build_server` (`mcp/server.py:18`) | [`mcp.md`](mcp.md) | `unit/test_mcp_tools.py`, `integration/test_mcp_server.py` |
| Assistant | `Assistant` (`application/assistant.py:133`), `chat_stream` (`api/assistant_routes.py:190`), web `useAssistant` (`assistant/useAssistant.ts:29`) | [`assistant.md`](assistant.md) | `unit/test_assistant.py`, `integration/test_assistant_api.py` |
| Agent OpenAPI | `agent_openapi` (`api/agent_openapi.py:102`); the routes marked with `AGENT` | [`openapi.md`](openapi.md); `openapi/agents.openapi.json` | `integration/test_agent_openapi.py` |
| Caches | Committed cut cache: `web/public/cache/`, built by `build_cache_workflow` (`application/cache_builder.py:26`), read by `loadTimeline` (`cascade/api.ts:21`). Raw HTTP downloads: `CachedHttp` (`infrastructure/http.py:26`) into `data/raw/` (git-ignored). Live runs: `RunCache` (`application/run_experiment.py:55`) (LRU). Sessions: three LRUs in `SessionService` (`application/sessions.py:82`) | [`engine.md`](engine.md) "Run", [`backend/README.md`](../backend/README.md) | `unit/test_grid_simulation.py` (cache against engine), `unit/test_run_persistence.py` |
| Data pipeline | `cascadasen-build`: `main` (`cli.py:13`) runs `BuildGridSnapshot` (`application/build_grid.py:18`) (sources in `infrastructure/sources/`, `GridUnifier` (`domain/unify.py:86`), `validate_snapshot` (`domain/validation.py:95`)). Operating points and base case: `data/scripts/build_operating_points.py`, then `data/scripts/build_baseline_opf.py` | [`datasets.md`](datasets.md) section 0, [`backend/README.md`](../backend/README.md) | `unit/test_unify.py`, `validation/test_real_snapshot.py` |
| Health index and cost | `prefault_health` (`domain/cascade/health.py:244`), `outage_cost` (`domain/simulation/consequence.py:32`) | [`health.md`](health.md), [`engine.md`](engine.md) "Cost" | `unit/test_health.py`, `validation/test_health_25f.py` |
| Prepared scenarios (batch changes) | `prepare_workflow` (`application/grid_stress.py:55`) | [`stress.md`](stress.md) | `unit/test_grid_stress.py` |
| Rate limits and locks | `TokenBucket` (`api/limits.py:23`), `SessionLocks` (`api/limits.py:72`) | [`sessions-api.md`](sessions-api.md) section 8 | `unit/test_session_locks.py` |
| Layering rule | `KNOWN_EXCEPTIONS` (`unit/test_architecture.py:22`) | [`adr/0005`](adr/0005-hexagonal-layering.md), [`architecture.md`](architecture.md) section 2 | `unit/test_architecture.py` |
| Tests | `backend/tests/{unit,integration,validation}/`, `web/src/**/*.test.ts(x)` | [`code-map.md`](code-map.md) section 5 | run commands in [`for-reviewers.md`](for-reviewers.md) section 1 |
| CI | `.github/workflows/checks.yml` (pytest with coverage floor, mypy, web), `lint.yml` (ruff, changelog), `deploy.yml` (needs `checks`) | [`infrastructure.md`](infrastructure.md) "Automatic deploy from GitHub" | the workflows run the tests above |
| Repository index | `scripts/build_index.py` writes `docs/index/repo-index.json` | [`index/README.md`](index/README.md) | `test_committed_index_matches_the_repository` (`integration/test_repo_index.py:36`) |
| Guardrails (no ranking, no technique) | `EXCLUDED` (`mcp/toolbox.py:20`), `MAX_CUT_LINES` (`application/sessions.py:39`), `SYSTEM` (`api/assistant_routes.py:38`) | [`cyber.md`](cyber.md) section 8 | `unit/test_mcp_tools.py`, `unit/test_incidents.py` |
| Deployment | `infrastructure/*.tf`, `infrastructure/deploy.sh`, `infrastructure/docker/` | [`infrastructure.md`](infrastructure.md), [`docker.md`](docker.md) | none |

Other entry points: [`../README.md`](../README.md) (product and repository map), [`../CHANGELOG.md`](../CHANGELOG.md) (what changed, newest first, written for agents), [`../backend/README.md`](../backend/README.md), [`../web/README.md`](../web/README.md).
