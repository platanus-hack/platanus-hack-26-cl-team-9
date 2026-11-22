# Changelog
Written for agents. Newest entry first. Each commit adds one entry at the top, using the format in `AGENTS.md` section 3. Read the newest entries before planning or changing anything. They record what changed after the docs were written.

## 2026-11-21 · feat(web): assistant API client and hook

- **Changed:** New `web/src/assistant/assistantApi.ts`: `streamChat(body, onEvent, signal)` reads `POST /api/v1/assistant/chat/stream` with `fetch` and the SSE parser and resolves whether the stream ended with `done`/`error`; `getConversation`, `deleteConversation`; `AssistantError(status, retryAfter, detail)` (status 0 = network) whose message is the Spanish text.
- **Changed:** New `web/src/assistant/useAssistant.ts`: `useAssistant(session)` → `{state, busy, enabled, restoring, send, reset}`. Sends `session_id: s.sid` with every message, joins the `session_id` of `start`/`tool_result`/`done` when it differs from the one on screen, reloads the session 300 ms after each successful edit/cut/repair, and after `step` fetches the run snapshots and annotates the card. The conversation id lives in `localStorage` (`sub50.assistant.cid`) and is rebuilt on mount (404 forgets it).
- **Why:** The chat panel (#73) needs the stream, persistence and the map following the assistant.
- **Agents:** A 503 disables the chat (`enabled = false`). A stream that drops before `done` marks the turn interrupted and re-reads the conversation up to 5 times, 3 s apart. `reset()` aborts the stream, clears the chat and DELETEs the conversation (the session stays). `errorText` in `sessionApi.ts` was not exported: all assistant texts come from `labels.ts`. Tests: `assistantApi.test.ts`.
- **Files:** `web/src/assistant/{assistantApi.ts,assistantApi.test.ts,useAssistant.ts}`.

## 2026-11-21 · feat(web): reduce assistant events to steps

- **Changed:** New `web/src/assistant/steps.ts`: pure chat state (`ChatState`, turns, steps, `ToolCard`) with `begin`, `reduce(state, event)`, `interrupt`, `fail`, `annotate` and `fromConversation(view)`.
- **Changed:** New `web/src/assistant/labels.ts`: Spanish tool names for the 23 MCP tools (`toolName`), readable arguments (`argsText`), short result summaries (`resultText`), `refreshFor(tool)` → `"network" | "state" | "snapshots" | null`, and error texts per status (`errorMessage`, `truncatedText`).
- **Why:** The chat panel (#73) shows each step live, grouped by `step`, with tool cards that go from running to ok or failed.
- **Agents:** A result pairs with its call by `id`; `done` and `error` turn cards still running into failed. `GET /conversations/{cid}` does not say which turn ran each tool, so `fromConversation` merges the assistant texts of one user message into one turn (last text = reply) and puts the tool trace in `restoredTools`. Summaries only repeat fields the tool returned. Tests: `steps.test.ts`, `labels.test.ts`.
- **Files:** `web/src/assistant/{steps.ts,labels.ts,steps.test.ts,labels.test.ts}`.

## 2026-11-21 · feat(web): parse the assistant event stream

- **Changed:** New `web/src/assistant/sse.ts` with `createSseParser(onEvent)`: `push(chunk)` parses `text/event-stream` chunks cut anywhere into `{event, data}`; `flush()` parses a last block left without a blank line.
- **Why:** First piece of the assistant chat in the web (#73). `EventSource` only does GET, so the POST `/api/v1/assistant/chat/stream` is read with `fetch` and this parser.
- **Agents:** It skips `: ping` comments and blocks without `event:`, accepts `\r\n` (also split between chunks), joins multi-line `data:` with `\n`, and passes non-JSON data as a string. Tests in `sse.test.ts`.
- **Files:** `web/src/assistant/{sse.ts,sse.test.ts}`.

## 2026-11-21 · docs(mapa3): document Prender todo

- **Changed:** `docs/mapa3.md`. §3 places the control next to the layers button. §4 gets new item 9, **Prender todo**: what it clears, what it keeps, when it is disabled. The placeholder tabs become item 10. §8 adds `powerAll.ts` to the file table. §11 adds the session behaviour: confirm, repair every open line for everyone, dataset edits kept.
- **Why:** The docs have to match the button from the previous commit.
- **Agents:** No new rules beyond the previous two entries.
- **Files:** `docs/mapa3.md`.

## 2026-11-21 · feat(web): add Prender todo button to mapa 3

- **Changed:** `CascadeApp.tsx` renders a labelled button **Prender todo** (bolt icon) at the top right, left of the `.map-controls` column, on the layers button's row. It sits outside every tab/view branch, so it shows from Red, Simulación, Datos, Ayuda, Fuentes and Sesión. It is enabled when `canPowerAll({ cuts, edited: false })` holds, i.e. while any cut is in force (local cut or the session's open lines).
- **Changed:** `powerAllOn()`. Without a session it applies `powerAll(...)`: no cut, no selection, no notice, timeline at 0 and paused, same point. In a session it asks `confirm(...)` first, then calls the existing `restore()` (`repairLines(sid, { all: true }, rev)` via `s.edit`) and clears the selection and the timeline. Tab, colour mode and view never change. Session dataset edits are kept.
- **Why:** Before this, "Reponer línea" in the selection or impact card was the only way back to the base case, and it repaired a single cut. With several elements switched off (#42, PR #67) the user needs one always-visible way back to the starting point that keeps the chosen operating point.
- **Agents:** Disabled is `aria-disabled` with a guarded click, not `disabled`, so `TipLayer` still shows "No hay nada apagado ni editado." (same pattern as the placeholder tabs). `.power-all` has z-index 2, below `.map-controls` (3), so the layers popover covers it while open. No red: red is reserved for failure. Open PR #67 (`sub-<bus>` cut ids) needs no special handling: `cut: null` clears it too, but expect a textual merge conflict in the same area of `CascadeApp.tsx`. When #42 phase B adds local edits, pass them as `edited`. Known nit: after a click the tooltip keeps its old text until the pointer leaves the button (TipLayer reads `data-tip` only on `pointerover`).
- **Files:** `web/src/cascade/{CascadeApp.tsx,cascade.css}`.

## 2026-11-21 · feat(web): add pure powerAll helpers for mapa 3

- **Changed:** New `web/src/cascade/powerAll.ts` with `canPowerAll({ cuts, edited })` (true when there is at least one cut or `edited`) and `powerAll(view)`, which keeps `pointId` and returns `cut: null`, `selection: null`, `t: 0`, `playing: false`.
- **Why:** The "Prender todo" button (next commit) needs a tested rule for when it is enabled and for what it resets.
- **Agents:** A selection or a timeline position alone does not enable the button. `edited` is always `false` for now; #42 phase B (local value edits) plugs in there. Tests are in `web/src/cascade/powerAll.test.ts`.
- **Files:** `web/src/cascade/{powerAll.ts,powerAll.test.ts}`.

## 2026-11-22 · feat(infra): ECS task of 4 vCPU and 8 GB
- **Changed:** `aws_ecs_task_definition.app` goes from 2 vCPU / 4 GB to 4 vCPU / 8 GB (`cpu = 4096`, `memory = 8192`, a valid Fargate pair). `docs/infrastructure.md` says so.
- **Why:** The user asked for a bigger task. The Fargate On-Demand vCPU quota is 30, so two 4 vCPU tasks fit during a blue/green rollout.
- **Agents:** The service has `ignore_changes = [task_definition]`, so the new size only reaches it after a one-time `aws ecs update-service --task-definition cascadasen:<revision>` that points at the revision Terraform registers; CI deploys copy that revision and keep the size.
- **Files:** `infrastructure/ecs.tf`, `docs/infrastructure.md`.
## 2026-11-21 · feat(web): shut down a substation from its card

- **Changed:** The substation card has **Apagar esta subestación** ("Abre sus N líneas en t = 0.") and, while it is shut down, **Encender subestación**. Without a session it sets the cut to `sub-B###` and plays `<point>/sub-B###.json`; in a session it opens the substation's closed lines in one `POST /{sid}/cut` and repairs exactly those lines to power it on.
- **Changed:** `text.ts` adds `SUBSTATION_PREFIX`, `shutdownNode`, `substationLines`, `cutName` ("Subestación Polpaico" or the line name) and a plural `line_cut` narration ("Salen de servicio las líneas A, B y C."). The impact card (`Corte: Subestación ...`, button **Encender subestación**) and the Escenarios row use `cutName`.
- **Why:** Second kind of scenario asked by the user: shutting down a substation = opening every line of it at t = 0.
- **Agents:** A static `cut` is `R###` or `sub-B###`, and `?cut=sub-B012` works; the hour change in Escenarios and the missing-file fallback are unchanged. Sessions have no `sub-` id, only open lines. Verification: `npm test` 55 passed, `npm run build` ok. "Bloquear" is still out of scope.
- **Files:** `web/src/cascade/{text.ts,text.test.ts,SelectionCard.tsx,CascadeApp.tsx,SimulationPanel.tsx,Scenarios.tsx}`, `docs/mapa3.md`.

## 2026-11-21 · chore(cache): regenerate the cache with substation cuts

- **Changed:** `web/public/cache/` regenerated with `uv run cascadasen-cache`: 752 new `sub-B###.json` (188 per point) and the 1,097 existing files rewritten. Size went from 23 MB to 42 MB (`du -sh`); the docs say so.
- **Why:** The web reads substation shutdowns from the cache. The existing files were stale: they lacked the newer summary fields (`final_hz`, `rocof_hz_s`, `inertia_mws`, `shed_mw`, `battery_mw`, `uncertain`, `prefault_boundary_mw`) and the current assumption texts, so line cuts now match the engine too.
- **Agents:** Checked: `nov2026-1300/sub-B012.json` has `failed_elements` = `["R042","R043"]`, the two lines of B012, and its first event is `line_cut` with both ids at t = 0. A full run takes about a minute.
- **Files:** `web/public/cache/`, `docs/mapa3.md`, `docs/engine.md`, `web/README.md`.

## 2026-11-21 · fix(hooks): find a staged CHANGELOG.md in commits with many files

- **Changed:** `scripts/hooks/pre-commit` pipes the staged list into `grep -x ... >/dev/null` instead of `grep -qx`.
- **Why:** With `pipefail`, `grep -q` exits at the first match, `printf` dies of SIGPIPE and the check reported "CHANGELOG.md is not staged" on a commit of ~1,850 files (the cache regeneration) even though it was staged.
- **Agents:** Large commits such as a regenerated `web/public/cache/` now pass the hook without `SKIP_CHANGELOG`.
- **Files:** `scripts/hooks/pre-commit`.

## 2026-11-21 · feat(cache): precompute a cut per substation

- **Changed:** `cascadasen-cache` also writes `<point>/sub-B###.json` for each of the 188 substations: the cascade for opening every line of that bus at t = 0 (`run_cascade_workflow(net, op, ids)`). Buses without lines are skipped (none today). The printed count per point is now `{"lines": 273, "substations": 188}`.
- **Why:** The map gets a second kind of scenario, "Apagar esta subestación" (user decision: shutting down = opening all its lines at t = 0). Without a session the web only reads precomputed files.
- **Agents:** A scenario id in the cache is now either a line id `R###` or `sub-B###`; both files share the timeline format. The cache is regenerated in the next commit. "Bloquear" (loss of control) is not modelled.
- **Files:** `backend/src/cascadasen/application/cache_builder.py`, `docs/mapa3.md`, `docs/engine.md`, `web/README.md`.

## 2026-11-21 · docs(mapa3): document the clean default URL

- **Changed:** `docs/mapa3.md` §2: the URL carries only values that differ from the defaults, a bare `/` is the default view, and `?point=nov2026-1300` is normalised away. §11: a session URL drops `point` as well as `cut`.
- **Why:** The docs have to match `syncedSearch` from the previous commit.
- **Agents:** No new rules beyond the previous entry.
- **Files:** `docs/mapa3.md`.

## 2026-11-21 · fix(web): keep the mapa 3 URL clean on defaults

- **Changed:** New `web/src/cascade/url.ts` with `DEFAULT_POINT` (`nov2026-1300`) and the pure `syncedSearch(search, { pointId, cut, mode, sid })`. `_syncUrl` in `CascadeApp.tsx` uses it and keeps `location.hash`. The URL now writes `point` only when it differs from the default and there is no session, `cut` only without a session, and `vista=3d` only in 3D. It keeps every other param (`sesion`, `mapa`, `limite`) and drops the `?` when nothing is left.
- **Why:** The first render of `/` became `/?point=nov2026-1300`, and an empty search still left a trailing `?`. Explicit `?point=`/`?cut=`/`?vista=3d` links still open the same state.
- **Agents:** A bare `/` is the default view. A session URL carries `sesion` (and `vista`) but no `point` or `cut`. Tests are in `web/src/cascade/url.test.ts`. No slug or path aliases (such as `/25f`): ids stay the only deep-link format. Note: `scripts/lint.sh` only lints `frontend/*`, so `web/` files are not linted.
- **Files:** `web/src/cascade/{url.ts,url.test.ts,CascadeApp.tsx}`.

## 2026-11-21 · docs(network): add network-format.md and update regional and datasets docs

- **Changed:** New `docs/network-format.md`, the data contract for adding or uploading a network, in seven sections:
  1. Fields, types, units, ISO3 and provenance per bus, line, DC link and plant.
  2. Readiness levels L0 / L1 / L1+ / L2.
  3. Gap filling, with the error measured on Brazil.
  4. Worked examples: Chile, Brazil, Peru, Argentina and Bolivia.
  5. A checklist to add a country.
  6. Upload safety (#49 part C).
  7. What each level can claim.
- **Changed:** `regional.md` gets section 6 (Brazil flow network: sources, units, decisions, result) and fixes section 4: ONS `SUBESTACAO.csv` **has** coordinates. `datasets.md` adds sources [42] and [43] (ONS, CC BY, downloaded 2026-11-21). `architecture.md`, `plan.md` §9 item 14, `backend/README.md` and the AGENTS.md read order (item 10) mention the new pieces.
- **Why:** Issue part B. The contract has to be followable without reading the code, and it has to say how much a deduced network can be trusted.
- **Agents:** Expected error of a deduced network, from Brazil:
  - x: median 15 %, p90 39 %;
  - capacity with Chile's typical ratings: median 31 %, p90 62 %;
  - distance-snapped topology: precision 89 %, recall 99 %.

  Treat these as a lower bound for the OSM countries. The proposed upload limits (10 MB, 5,000 buses, 10,000 lines) are not enforced anywhere yet.
- **Files:** `docs/{network-format,regional,datasets,architecture,plan}.md`, `AGENTS.md`, `backend/README.md`.

## 2026-11-21 · feat(data): build Brazil flow network from ONS

- **Changed:** New `data/processed/latam/BRA/network.json` (730 KB): 853 buses, 1,305 AC lines (1,842 circuits, 230-765 kV), 4 HVDC links (12 records) and 495 plant groups. `manifest.json` gains `countries.BRA.flow`. The drawn BRA geojson files are unchanged, except that the manifest's EPE `fetched_at` was refreshed.
- **Changed:** New `backend/tests/validation/test_ons_network.py` (skips without the file). It checks provenance on every element, x > 0 and capacity > 0, a unit guard (the median ohm/km per kV must sit inside `X_PER_KM`), the main component ≥ 95 %, length within ±15 % of 189,308 km, coordinate match ≥ 98 %, and that the manifest counts match the file.
- **Why:** Issue part A3/A4. The figures: AC 174,428 circuit-km (−7.9 %) and AC+DC 196,456 km (+3.8 %) against 189,308 km. Coordinates come from ONS for 853 of 855 substations (USIBA 230 kV and COL BOA SORTE 2 500 kV have none, and neither is in EPE). 215 circuits use an assumed capacity. 18 lines with a foreign end are excluded.
- **Agents:** A5 result (also in the manifest):
  - Deduced x is off by a median of 15 % (p90 39 %); deduced capacity by a median of 31 % (p90 62 %).
  - The distance-snapped drawn corridors have precision 0.89 and recall 0.99 against the ONS corridors, on the 728 substations both layers share.
  - ONS coordinates match EPE substations of the same name within a median of 50 m (582 pairs, 9 more than 10 km apart).
  - HVDC MW are `kV × A` per record: Xingu gives 4,200 MW per bipole (4,000 nominal), but Madeira gives 12,600 MW (6,300 nominal), so DC MW are unverified. Itaipu HVDC states no amperes (`capacity_mw: null`).
- **Files:** `data/processed/latam/{BRA/network.json,manifest.json}`, `backend/tests/validation/test_ons_network.py`.

## 2026-11-21 · feat(regional): write BRA/network.json with cascadasen-regional --ons

- **Changed:** `cd backend && uv run cascadasen-regional --countries BRA --ons` now also builds Brazil's flow network through the new use case `BuildFlowNetwork` (`application/build_regional.py`, wired by `container.flow_network_use_case`). It writes `data/processed/latam/BRA/network.json` and a `flow` block under `manifest.countries.BRA`. That block has counts, circuit-km per kV, the length check against 189,308 km, assumed values, exclusions, the coordinate match rate and `deduction_error`. The command prints a summary and every warning.
- **Changed:** `BuildRegionalGrid` keeps a country's existing `flow` block when it rewrites the drawn layer.
- **Why:** Issue part A3: one command produces the network file and the figures the docs cite.
- **Agents:** `--ons` needs `BRA` in `--countries`. It reads the EPE layer (cached raw) for plants, the name fallback and the A5 topology check. `as_of` defaults to the UTC build date. The ONS CSVs are cached in `data/raw/regional/bra/ons_*.csv` (git-ignored); `--refresh` downloads them again.
- **Files:** `backend/src/cascadasen/application/build_regional.py`, `backend/src/cascadasen/infrastructure/container.py`, `backend/tests/unit/test_ons_brasil.py`.

## 2026-11-21 · feat(regional): add ONS adapter and pure flow-network builder for Brazil

- **Changed:** New `domain/regional_network.py` (pure). It turns ONS line and substation rows into a flow network: one bus per ONS substation (`id_subestacao`), AC circuits folded like Chile's `_parallel`, HVDC records as `dc_links`, and EPE plants attached by distance. It also holds `deduction_error`, which compares typical x and capacity, and the distance-snapped drawn topology, against the real values (issue part A5). New adapter `infrastructure/sources/regional/ons_brasil.py` reads `LINHA_TRANSMISSAO.csv` and `SUBESTACAO.csv`. New port `FlowNetworkSource`; settings `ons_lines_url` and `ons_substations_url`.
- **Why:** Brazil was only a drawn layer. ONS declares each line's two bus numbers and positive-sequence r, x and shunt, and `SUBESTACAO.csv` gives each bus a substation **and coordinates** (older docs say it has none). Line ends no longer need to be guessed.
- **Agents:**
  - ONS states no units. From the magnitudes, r and x are percent on 100 MVA and shunt is Mvar at nominal voltage (ANAREDE), so `x_pu = val_reatancia / 100` with no kV conversion.
  - The thermal base is `val_capacoperlongacomlimit` (long duration, with limiting factor). Missing amperes, including 0 A, use the ONS median MW per circuit at the same kV and are marked `assumed_fields: ["capacity_mw"]`.
  - Lines that are deactivated or enter service after `as_of` are excluded, as in `_built_by`. *Ramal* rows and line ends outside the ONS registry (Uruguay, Argentina, Paraguay, Venezuela) are dropped with a warning naming the substation and kV.
  - `regional_reduction._km` and `_nearest` are now public as `km_xy` and `nearest`.
- **Files:** `backend/src/cascadasen/domain/{regional_network,regional_reduction,ports}.py`, `backend/src/cascadasen/infrastructure/{settings.py,sources/regional/ons_brasil.py}`, `backend/tests/unit/test_ons_brasil.py`.

## 2026-11-21 · docs(assistant): document the step stream for map clients

- **Changed:** `docs/assistant.md` section 2b: the events of `POST /chat/stream` with examples, which session routes to fetch after each tool to draw, pings and the 90 s stream deadline, disconnect behaviour, a `fetch` reader for browsers (`EventSource` only does GET) and a `curl -N` example. `docs/stack.md` 7.3 lists the route.
- **Why:** The frontend will build partial map views on these events.
- **Agents:** Live check on Bedrock reached only the error path (the temporary credentials had expired): `start` arrives at once and the model failure arrives as an `error` event. The full flow is covered by the toy-world tests.
- **Files:** `docs/assistant.md`, `docs/stack.md`.

## 2026-11-21 · feat(api): stream the assistant's steps as Server-Sent Events

- **Changed:** `POST /api/v1/assistant/chat/stream` takes the `/chat` body and answers `text/event-stream`: `start`, `assistant_text`, `tool_call`, `tool_result` (compact result plus `session_id` and `run_id`), then `done` (the `/chat` fields without the trace) or `error` (`status`, `detail`). A `: ping` comment goes out after `assistant_stream_ping_s` (10 s) without events. The loop runs in a worker thread and keeps going, and saves the conversation, if the client disconnects. `/chat` is unchanged; both share the rate limit (`admit`) and the tool wiring (`toolbox_factory`).
- **Changed:** New settings `assistant_stream_deadline_s` (90 s: events and pings keep CloudFront's 30 s origin read timeout from firing) and `assistant_stream_ping_s`.
- **Why:** The web will draw partial results on the map while the assistant works. Events stay light and point to the existing routes for the full data: after `cut_lines` `GET /sessions/{sid}/state` (timeline with frames), after `step` `GET /sessions/{sid}/runs/{rid}/snapshots?start=N`, after an edit `GET /sessions/{sid}/network` (user decision: references, not map data inside the events).
- **Agents:** Errors found before streaming (422, 404 conversation, 429, 503) are plain HTTP errors; later ones are `error` events. The route is not marked `x-sub50-agent`. Verification: `uv run --extra mcp pytest -q` 349 passed, 2 skipped; lint clean. Not tried against Bedrock yet.
- **Files:** `backend/src/cascadasen/api/assistant_routes.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/tests/integration/test_assistant_api.py`.

## 2026-11-21 · feat(assistant): emit each step of the tool loop through a callback

- **Changed:** `Assistant.chat` takes `on_event(kind, data)` and `deadline_s`. It emits `start` (`conversation_id`, `session_id`, `run_id`), `assistant_text` (`step`, `text`) when the model talks while calling tools, `tool_call` (`step`, `id`, `name`, `arguments`) and `tool_result` (`step`, `id`, `name`, `ok`, `result`, plus the current `session_id` and `run_id`). `Emitter` drops a callback that raises, so a client that goes away never stops the loop or the save.
- **Why:** The web wants to draw partial results on the map while the assistant works (next commit streams these events over SSE).
- **Agents:** Without `on_event` nothing changes for `/chat`. `deadline_s` overrides `assistant_deadline_s` for one message.
- **Files:** `backend/src/cascadasen/application/assistant.py`, `backend/tests/unit/test_assistant.py`.

## 2026-11-22 · fix(infra): bake data/processed at /data/processed in the backend image
- **Changed:** `backend.Dockerfile` copies `data/processed` to `/data/processed` (it copied it to `/data`). `docs/infrastructure.md` says so.
- **Why:** The code reads `CASCADASEN_DATA_DIR/processed/grid_snapshot.json`, so with the old layout production answered 503 "No hay snapshot de la red" on `/api/v1/nodes`, `/sim/*` and `/sessions` (health said `sin snapshot`). Local compose mounts `./data` at `/data`, so it never showed. Mapa 3 reads the static cache and was not affected.
- **Agents:** Any endpoint that needs the grid snapshot only works in the deployed image from this commit on. Check `GET /api/v1/health`: `status` must be `ok`.
- **Files:** `infrastructure/docker/backend.Dockerfile`, `docs/infrastructure.md`.
## 2026-11-21 · fix(assistant): guard the tool loop against lost events, invented MW and unkept promises

- **Changed:** `SessionTools` opens an `open_field` run when `inject_event` or `submit_action` arrive with no active run, and refuses `add_datacenter`/`add_generator` with MW the user never wrote (`numbers`, `stated`). `Assistant.loop` adds one hidden nudge when the model promises an action and stops (`announces`, `NUDGE`; hidden turns are left out of `view`), predicts the deadline with the mean call duration, and the trace carries each call's `arguments`. The factory is now `toolbox_for(session_id, run_id, said)`, where `said` is everything the user wrote in the conversation.
- **Changed:** System prompt as a list of rules: never ask the user to run tools, act in the same turn, numbers and causes only from results, separate new from previous overloads, no tool names in replies, say explicitly that it does not search the worst case, be brief.
- **Why:** Live bench on Bedrock and the 188-bus network (`docs/assistant.md` section 5). Seen there: an event injected before `start_run` was lost and then reported as applied; 150 and 500 MW invented for "un datacenter en Calama"; "la cortaré" with no cut; a 31 s message.
- **Agents:** `deepseek.v3.2` passed the whole bench several times and is set in the local `backend/.env` (not committed); Qwen3-Next failed intermittently. The bench script lives outside the repo. Verification: `uv run --extra mcp pytest -q` 298 passed, 2 skipped; lint clean.
- **Files:** `backend/src/cascadasen/{application/assistant.py,mcp/toolbox.py,api/assistant_routes.py}`, `backend/tests/{unit/test_assistant.py,integration/test_assistant_api.py}`, `docs/assistant.md`.

## 2026-11-21 · fix(mcp): tool results the model cannot misread

- **Changed:** Edit tools return where the element went (`bus`, `bus_name`, `area`, `area_name`) and the baseline as `newly_overloaded`, `still_overloaded`, `no_longer_overloaded`, `overloaded_now_total` (the edit results no longer carry `overloaded_lines`). `describe_network` lists corridors with their lines, annotates added loads and generators with their area, and with `focus` returns the area totals and its overloaded lines. `step` adds `unserved_mw` and `level_text` per cycle, `events_applied` and a `warning` when no event happened; `run_report` adds `worst_level_text`; `list_options` describes each template (scripted events, adversary, horizon).
- **Changed:** Tool descriptions: pass places by name and never guess ids, an area is enough for a bus, a corridor is not a line (open it with `inject_event` in a run), keep `open_field` unless another template is named, ask for missing MW, `unserved_mw` is power not energy, show after-action lines verbatim.
- **Why:** Live tests with Qwen3-Next and DeepSeek V3.2 on Bedrock (`docs/assistant.md` section 5) showed the model labelling the post-edit list as "already overloaded", guessing area ids (Santiago as A07), inventing a line id "R0607" for a corridor, picking a template with scripted events, adding MW across cycles into "GWh" and inventing a bus location.
- **Agents:** `docs/mcp.md` section 3 lists the new keys. Clients of the MCP edit tools that read `baseline.overloaded_lines` must use `newly_overloaded` plus `still_overloaded`. `digest.py` imports `LEVELS_ES` from `domain/theater/narrative.py`.
- **Files:** `backend/src/cascadasen/mcp/{tools,digest}.py`, `backend/tests/{unit/test_mcp_tools.py,integration/test_mcp_server.py}`, `docs/mcp.md`.

## 2026-11-21 · fix(theater): separate the two figures of one after-action summary line

- **Changed:** `TemplateInterpreter.after_action` writes "Decisiones innecesarias: 1; reserva operacional final: 57 %." instead of "Decisiones innecesarias: 1. Reserva operacional final: 57 %.".
- **Why:** In live tests the assistant read "1. Reserva…" as list numbering and wrote that the organisation "kept the reserve at 57 % without justification", which the report does not say.
- **Agents:** Text only; no key or number changed. Clients that parse this summary line by its old wording must update.
- **Files:** `backend/src/cascadasen/domain/theater/narrative.py`.

## 2026-11-21 · fix(mcp): report which overloads an edit caused

- **Changed:** Every edit tool (`add_datacenter`, `add_generator`, `add_line`, `add_bus`, `edit_element`, `remove_element`, `reset_network`) reads the overloaded lines before the edit and returns `baseline.newly_overloaded` and `baseline.no_longer_overloaded` next to `overloaded_lines`. The assistant's prompt asks the model to separate what the edit caused from what was already overloaded.
- **Why:** The assistant said a 120 MW datacenter in Antofagasta "sobrecarga" eight lines, but R014, R045, R122 and R247 were already over capacity in the untouched base case. The tools returned only the list after the edit, so the model could not tell.
- **Agents:** `baseline.overloaded_lines` alone is not the effect of an edit. Edit tools now make one extra `GET /network` before the edit (datacenter and generator reuse the one they already did).
- **Files:** `backend/src/cascadasen/{mcp/tools.py,api/assistant_routes.py}`, `backend/tests/integration/test_mcp_server.py`, `docs/mcp.md`.

## 2026-11-21 · fix(api): keep the waiter cap of 10 and document the threadpool trade-off
- **Changed:** Reverts the cap of 5 from the entry below: `session_lock_max_waiters` and `SessionLocks` default to 10 again, and the 409 text, agent spec, `docs/sessions-api.md` and `docs/stack.md` say 10 (spec regenerated). The `SessionLocks` docstring and `docs/sessions-api.md` section 7 now state the trade-off: one busy session holds up to 11 of AnyIO's 40 sync workers, and four busy sessions can delay every sync route, including the health check.
- **Why:** The cap of 10 is a user decision (entry "retry the busy 409 in the web client and raise the waiter cap to 10"); review pass 3 allowed keeping it if the trade-off is written down.
- **Agents:** Do not change the cap without asking the user. If the pool fills in production, lower `CASCADASEN_SESSION_LOCK_MAX_WAITERS` or raise the AnyIO thread limit.
- **Files:** `backend/src/cascadasen/api/{limits,session_routes,agent_openapi}.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/tests/unit/test_session_locks.py`, `docs/{sessions-api,stack}.md`, `docs/openapi/agents.openapi.json`, `CHANGELOG.md`.
## 2026-11-21 · fix(api): lower the per-session waiter cap to 5
- **Changed:** `SessionLocks` and `session_lock_max_waiters` (`CASCADASEN_SESSION_LOCK_MAX_WAITERS`) default to 5 waiters instead of 10. The 409 text in `session_routes.ERRORS`, the agent spec description, `docs/sessions-api.md` and `docs/stack.md` say 5; the spec is regenerated.
- **Why:** Review pass 3: each waiter blocks one of AnyIO's 40 sync workers for up to 10 s, so with 10 four busy sessions could stall every sync route, including the health check. The web and MCP clients now retry the busy 409, so a small cap no longer leaves a browser on a stale network.
- **Agents:** One busy session holds at most 6 workers. Raise the cap only together with the AnyIO thread limit.
- **Files:** `backend/src/cascadasen/api/{limits,session_routes,agent_openapi}.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/tests/unit/test_session_locks.py`, `docs/{sessions-api,stack}.md`, `docs/openapi/agents.openapi.json`.
## 2026-11-21 · feat(web): session mode with select and double-click cut after merging PR #60
- **Changed:** Merged upstream/main at e0c3088 (PR #60: click selects, double click cuts, `SelectionCard`, "Reponer línea", keyed timeline loads). Session mode is re-applied on main's shell: a double click or **Sacar de servicio** calls `POST /{sid}/cut`; `restore(lines?)` repairs through `POST /{sid}/repair` in a session (the selection card repairs the selected open line, the impact card and **Reparar todo** repair every open line).
- **Changed:** `SimulationPanel` takes `cuts: string[]` again ("Corte:" lists every open line; the button reads "Reponer líneas" when more than one is open). The session timeline is stored as `loaded = {key: "session"}` and a session state cancels a pending cache load. The map `onClick` calls `live.current.cutLine`, and the Datos pick mode runs before click interpretation.
- **Why:** PR #60 rewrote the click and cut flow in `CascadeApp.tsx`; session mode has to keep cutting and repairing through the session API.
- **Agents:** Without `?sesion=` the app is main's PR #60 behaviour (same single-cut output). `SelectionCard` in a session gets `cut` = the selected line when it is open.
- **Files:** `web/src/cascade/{CascadeApp,SimulationPanel}.tsx`, `docs/mapa3.md`, `CHANGELOG.md`.
## 2026-11-21 · feat(web): lock the Escenarios tree in a session after merging PR #57
- **Changed:** Merged upstream/main at f16cb09 (PR #57: line colors, `ScenarioTree` in the rail, time pill removed). `ScenarioTree` takes `cuts: string[]` instead of `cut` and an optional `locked` tip. Outside a session `CascadeApp` passes `cuts={cut ? [cut] : []}` and no `locked`, so the rail behaves as on main.
- **Changed:** In a session `locked` is the PINNED tip: scenario rows only fold and unfold, every condition except the session's point is `aria-disabled` with the tip, and no click calls `open`. "Corte ..." names every open line of the session. The dead `.time-pill` and `.scenario[aria-disabled]` rules in `web/src/session/session.css` became a `.condition[aria-disabled]` rule.
- **Why:** PR #57 removed the time pill and scenario buttons that pinned the operating point in a session; the user's rule is that a session fixes its point.
- **Agents:** Do not reintroduce a point switcher in session mode; `docs/mapa3.md` section 11 describes the locked tree. The `TimelineCard` clock now uses `clock(point?.snapshot, t).tenths` as on main.
- **Files:** `web/src/cascade/{CascadeApp,Scenarios}.tsx`, `web/src/session/session.css`, `docs/mapa3.md`, `CHANGELOG.md`.
## 2026-11-21 · feat(infra): sessions bucket policy
- **Changed:** `infrastructure/s3.tf` adds `aws_s3_bucket_policy.sessions`: any principal of this AWS account (`aws:PrincipalAccount` condition) may Get/Put/Delete objects under `sessions/*` and `runs/*` and list the bucket. It depends on the public access block, which stays on.
- **Why:** The user wants the policy in PR #50 as written; it lets the task role, CI and admins read and write session documents without a per-role grant.
- **Agents:** Never applied here (no plan/apply in this work). The grant is account-wide, not scoped to the ECS task role; narrowing it is a separate decision.
- **Files:** `infrastructure/s3.tf`.
## 2026-11-21 · fix(web): retry the busy 409 in the web client and raise the waiter cap to 10
- **Changed:** `call()` in `web/src/session/sessionApi.ts` retries a 409 that carries `Retry-After` up to 2 times, after that wait (capped at 10 s), with the same method, headers and body. A 409 without `Retry-After` (another instance won the write) is not retried.
- **Changed:** `useSession` keeps the session when the first load still gets a busy 409 and retries it every 3 s with the note "La sesión está ocupada con otra solicitud. Se reintenta la carga en unos segundos."; network errors and 5xx still fall back to the base case.
- **Changed:** `session_lock_max_waiters` (`CASCADASEN_SESSION_LOCK_MAX_WAITERS`) defaults to 10 instead of 4 (`SessionLocks` default too).
- **Why:** Review of PR #50 pass 2: each browser sends 3 parallel GETs per refresh, so 2-3 browsers on one session went past the cap of 5 and got the busy 409 at once; the web client never retried it and a first load dropped the visitor to the base case. User decision: cap 10, web client honours `Retry-After`.
- **Agents:** Every web session request now absorbs up to 2 busy 409s (about 2 s). `loader.ts` still sends its 3 reads in parallel (running them one after another would change the loader's tested overlap rules). Docs: `docs/sessions-api.md` sections 7-9, `docs/stack.md`, `docs/mapa3.md` section 11; agent spec regenerated (`DESCRIPTION`, `ERRORS[409]`).
- **Files:** `web/src/session/{sessionApi,sessionApi.test,useSession}.ts`, `backend/src/cascadasen/api/{limits,session_routes,agent_openapi}.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/tests/unit/test_session_locks.py`, `docs/{sessions-api,stack,mapa3}.md`, `docs/openapi/agents.openapi.json`.
## 2026-11-21 · fix(web): open a session only from ?sesion=, keep a landed edit, neutral overlay warnings
- **Changed:** `useSession` no longer reads or writes `localStorage.sub50_session`; `sessionIdFrom(search)` takes the id only from `?sesion=`, so a bare `/` never calls `/api` (the URL still keeps `?sesion=` while in a session).
- **Changed:** `edit()` returns true once the write succeeded; a failed reload after it (for example a busy 409) shows "El cambio se guardó, pero no se pudo recargar la sesión: …" instead of failing the edit, so a form is not resubmitted into a duplicate element.
- **Changed:** Overlay warnings in **Datos** use `.note.warn` (neutral, `--selected` / `--fg-2` in `session.css`) instead of v5's red `.note`.
- **Why:** Review of PR #50: the localStorage fallback broke the user's "no /api calls without ?sesion=" rule and `web/README.md`; a reload failure after a successful add invited duplicates; design.md reserves red for faults.
- **Agents:** Do not reintroduce a stored session id; sharing and reload both rely on the URL. The "no /api without ?sesion=" check (with and without an old `sub50_session` key) belongs in the browser E2E step.
- **Files:** `web/src/session/{useSession,sessionApi,sessionApi.test}.ts`, `web/src/session/{DataPanel.tsx,session.css}`, `docs/{mapa3,sessions-api}.md`.

## 2026-11-21 · fix(api): cap the waiters per session and retry the busy 409 in the MCP client
- **Changed:** `SessionLocks(timeout_s, max_waiters=4)` (`api/limits.py`): when one request holds a session and 4 already wait, a further request gets the busy 409 (`Retry-After: 1`) at once instead of waiting. New setting `session_lock_max_waiters` (`CASCADASEN_SESSION_LOCK_MAX_WAITERS`, default 4).
- **Changed:** `Sub50Client.request` (`mcp/client.py`) retries a 409 that carries `Retry-After` once, for GET and non-GET, after that wait (capped at 5 s, `sleep` injectable); a 409 without it keeps the old rule (non-GET retried at once).
- **Why:** Review of PR #50: sync routes wait in threadpool workers (anyio default 40, shared by every sync route and the SSE pollers), and session reads have no rate limit, so a long holder plus refresh bursts could stall the process. Ricardo's MCP client (merged from the remote branch) ignored the new busy 409.
- **Agents:** Only the busy 409 carries `Retry-After`; a busy 409 means the request did not run, so retrying a POST is safe. Docs: `docs/sessions-api.md` sections 7-9, `docs/stack.md` 6.2 and 7.2, `docs/mcp.md`; agent spec regenerated (`DESCRIPTION`, `ERRORS[409]`).
- **Files:** `backend/src/cascadasen/api/{limits,app,session_routes,agent_openapi}.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/src/cascadasen/mcp/client.py`, `backend/tests/unit/{test_session_locks,test_mcp_tools}.py`, `docs/{sessions-api,stack,mcp}.md`, `docs/openapi/agents.openapi.json`.

## 2026-11-21 · fix(web): keep the network of a refresh that a run event overtakes
- **Changed:** New `web/src/session/loader.ts`: `createLoader(api, apply)` returns `{load, loadDoc, cancel}`. A full load applies network and state when it is the newest full load, and its session document only when no newer document read started. `useSession.ts` uses it (the `seq`/`docSeq` refs are gone; `leave()` calls `cancel()`); the `Session` interface is unchanged.
- **Why:** Review finding (PR #50, user task 3): a run event (`loadDoc`) during a dataset refresh made `load` return early and drop the new network and state, so the screen kept the old dataset.
- **Agents:** `web/src/session/loader.test.ts` covers the race with deferred promises (document read during a full load, two overlapping loads, cancel). Verification: `npx vitest run` 31 passed (8 files); `npm run build` ok.
- **Files:** `web/src/session/{loader,loader.test,useSession}.ts`, `docs/mapa3.md`.
## 2026-11-21 · feat(web): session mode in the Design v5 shell
- **Changed:** Session mode is wired into main's Design v5 `CascadeApp.tsx`: a rail item **Sesión compartida** (view with **Crear sesión** / **Unirse**, or the id, **Copiar enlace** and **Salir**), a panel-head strip in a session (`Sesión <id>`, `rev. N`, **en vivo** / **sondeo**, **Copiar enlace**), tabs **Red**, **Simulación**, **Datos** in a session (placeholder tabs hidden), line clicks through `POST /{sid}/cut`, and **Elegir en el mapa** pick mode.
- **Changed:** New `web/src/session/SessionCut.tsx` (**Líneas abiertas en la sesión · N**, **Reparar**, **Reparar todo**) above `SimulationPanel`, whose prop `cut` became `cuts: string[]`. In a session the time pill select and the rail scenarios are disabled with a tooltip and the URL drops `cut`.
- **Changed:** New `web/src/session/session.css` (imported after `cascade.css`): rules under `.shell`, radius 0, cascade.css tokens only, `.tag` / `.btn`. `SessionBar.tsx` takes `{ s, compact? }`; `DataPanel.tsx` only changed class names (`badge`→`tag`, `subtabs`→`seg`, `stats`→`figures`, `link`→`text-btn`, `muted`→`meta`).
- **Why:** User task 1 (PR #50 brief): PR #45 rebuilt the shell, so session mode goes into the new one instead of restoring the old shell. Without `?sesion=` the app is main's plus one rail item and makes no `/api` request.
- **Agents:** Never use `.badge` for session labels (`.shell .badge` is the event marker). `web/src/styles.css` holds no session rules. Docs: `docs/mapa3.md` section 11 and `web/README.md` describe the new labels. Verification: `npx vitest run` 28 passed (7 files); `npm run build` ok; Vite proxy smoke test (backend on :18731, `VITE_API_TARGET`, vite on :15731): `POST /api/v1/sessions` 201 with `session_id`, `/network` 200, `/cut` and `/repair` ok, `/` serves the app; both processes stopped.
- **Files:** `web/src/cascade/{CascadeApp,SimulationPanel}.tsx`, `web/src/session/{SessionBar,SessionCut,DataPanel}.tsx`, `web/src/session/session.css`, `docs/mapa3.md`, `web/README.md`.
## 2026-11-21 · feat(api): typed response models in the agent spec

- **Changed:** `api/agent_openapi.py` adds `AgentOut` (`extra="allow"`), `ok(model, code=200)` (a `responses=` entry whose description is the model's first docstring line) and a pass in `agent_openapi()` that keeps only the `$ref` of every 2xx JSON schema.
- **Changed:** New documentation-only models: `TheaterNetworkOut`, `CatalogOut`, `RunStateOut`, `RunEventOut`, `RunStepOut`, `RunActionOut`, `RunSnapshotsOut`, `RunTraceOut`, `RunReportOut`, `AfterActionOut`, `SessionRunOut(RunSummary)` in `simulation_schemas.py`; `SessionDocOut`, `SessionWarningOut`, `EditOut`, `SessionNetworkOut(TheaterNetworkOut)`, `CutStateOut` in `session_schemas.py`. Every agent route with an empty 2xx schema now declares one with `responses=ok(M) | <errors>`.
- **Why:** User task 4 (PR #50 brief): the future MCP wrapper needs output schemas. `response_model=` would validate and reorder bodies and `response_model=None` changes NaN handling, so routes keep their inferred `dict[str, Any]` and bodies are byte-for-byte unchanged.
- **Agents:** New agent routes document their body with `ok()` (docs/openapi.md convention 6). `test_every_success_response_names_its_model` fails when a 2xx body is not a bare `$ref` to a model with properties; `test_responses_match_the_documented_models` (in `test_sessions_api.py` and `test_runs_api.py`) validates real toy-world responses against the declared models, so a removed required key breaks it. Verification: `uv run pytest` 285 passed, 2 skipped, 1 failed (only the Bedrock test); `ruff check` and `ruff format --check` clean; agent spec regenerated.
- **Files:** `backend/src/cascadasen/api/{agent_openapi,simulation_schemas,session_schemas,simulation_routes,session_routes}.py`, `backend/tests/integration/{test_agent_openapi,test_sessions_api,test_runs_api}.py`, `docs/openapi.md`, `docs/openapi/agents.openapi.json`.

## 2026-11-21 · feat(api): serve one request at a time per session

- **Changed:** New `SessionLocks` in `api/limits.py` (one `threading.Lock` per session id, refcounted, so idle sessions leave no entry), on `app.state.session_locks`. Every `{sid}` route of `api/session_routes.py` holds it around its `session_call` through `serial(request, sid)`: get/delete session, reset, network, the 12 element routes, cut, repair, state and every `/runs` route. `GET /{sid}/events` (SSE) and `POST /sessions` do not take it. Rate limits and the repair 422 check run before the wait.
- **Changed:** A request waits up to `session_lock_timeout_s` (10 s, `CASCADASEN_SESSION_LOCK_TIMEOUT_S`), then gets 409 `"La sesión está ocupada con otra solicitud; reintenta."` with `Retry-After: 1`. The agent spec documents 409 on every sid route (`READ_ERRORS = errors(404, 409, 422)`, `delete_session` adds 409) and adds a "One request at a time" paragraph to its description.
- **Why:** User rule (PR #50 brief, task 2): a session handles only one request at a time. The wait plus 409 is the orchestrator's default. Store conditional writes and `If-Match` stay the guard across processes.
- **Agents:** The lock is per process; with several instances two requests on one session can still run at once on different instances. Routes are sync `def`, so a waiting request blocks a threadpool worker, not the event loop. New tests: `tests/unit/test_session_locks.py`, and three tests at the end of `tests/integration/test_sessions_api.py` (same session serial, two sessions parallel, held lock gives 409). Verification: `uv run pytest` 282 passed, 2 skipped, 1 failed (only the Bedrock test); `ruff check` and `ruff format --check` clean; agent spec regenerated.
- **Files:** `backend/src/cascadasen/api/{limits,app,session_routes,agent_openapi}.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/tests/{unit/test_session_locks.py,integration/test_sessions_api.py}`, `docs/{sessions-api,stack}.md`, `docs/openapi/agents.openapi.json`.
## 2026-11-21 · fix(assistant): open a session on first use and stop asking the user to call tools

- **Changed:** `SessionTools.run` (`mcp/toolbox.py`) opens a session the first time a tool that needs one is called with none active (all but `start_session`, `join_session`, `list_options`) and adds `nota` to that result. The assistant's system prompt says the user cannot run tools, so the model must call them itself.
- **Why:** With Qwen on Bedrock the model called `add_datacenter` first, got "No hay sesión activa" and told the user to run `start_session`, which they cannot. The MCP server is unchanged: there the client's model handles it.
- **Agents:** Auto-created sessions count against the session-creation limit (10 per hour per IP). `docs/assistant.md` section 3 says it.
- **Files:** `backend/src/cascadasen/{mcp/toolbox.py,api/assistant_routes.py}`, `backend/tests/{unit/test_assistant.py,integration/test_assistant_api.py}`, `docs/assistant.md`.

## 2026-11-21 · fix(assistant): log the AWS error behind a model failure

- **Changed:** `ConverseToolChat.turn` logs the model id and, for an AWS error, its code and message (`describe`), instead of only the exception name. The client still gets the fixed Spanish text.
- **Why:** A user got "El modelo de lenguaje no está disponible ahora" with Qwen on Bedrock and the log could not say whether it was credentials, access to the model, throttling or a timeout.
- **Agents:** To diagnose a 502 from `/api/v1/assistant/chat`, read the server log line `assistant LLM call failed for <model>: <Type>: <code> <message>`.
- **Files:** `backend/src/cascadasen/infrastructure/llm_tools.py`, `backend/tests/unit/test_llm_tools.py`.

## 2026-11-21 · docs(assistant): document the in-app assistant and the third LLM role

- **Changed:** New `docs/assistant.md` (turn it on, routes, how the loop and the in-process transport work, guardrails, what is not done). `docs/strategy.md` section 10 gets the assistant as a third LLM role; `docs/stack.md` gets section 7.3; `docs/mcp.md`, `backend/README.md` and `AGENTS.md` (read order) point to it.
- **Why:** `strategy.md` said the LLM only explains or plays C2; the assistant executes what the user asks on the user's own session, so the doc had to say so.
- **Agents:** Read `docs/assistant.md` before touching `api/assistant_routes.py` or `application/assistant.py`. Pending: a real run against Bedrock and the 188-bus network (to pick the `step` cap and check the 25 s deadline), Terraform for Bedrock permission and a longer CloudFront origin timeout, a daily cost cap per IP.
- **Files:** `docs/{assistant,strategy,stack,mcp}.md`, `backend/README.md`, `AGENTS.md`.

## 2026-11-21 · feat(api): assistant chat routes with rate limit and body cap

- **Changed:** `api/assistant_routes.py` adds `POST /api/v1/assistant/chat` (`{message 1-2000, conversation_id?, session_id?}` → `{conversation_id, session_id, run_id, reply, tool_calls, steps, truncated, notice}`), `GET` and `DELETE /api/v1/assistant/conversations/{cid}`. Each request builds its tools over `in_process_client(app, client_ip)` with `X-Sub50-Agent: asistente`. Limits: `rate_assistant_per_minute` (10) per client IP, and `BODY_LIMIT_PREFIXES` covers `/api/v1/assistant`. Errors: 503 when `CASCADASEN_LLM_ENABLED` is off or the provider is not `bedrock-converse`, 502 on a model failure (fixed Spanish text), 404, 409, 422, 429.
- **Why:** The in-app assistant: natural-language simulations through the same session routes an external agent uses, with no MCP client.
- **Agents:** The routes carry no `x-sub50-agent` mark, so `docs/openapi/agents.openapi.json` is unchanged. Internal tool calls pass through the real rate limits keyed on the caller's IP, so a chat message that makes many writes can hit 429 inside a tool (the model sees it and tells the user). `Settings` reads `backend/.env`: tests pass `llm_enabled=False` to stay hermetic. Verification: `uv run --extra mcp pytest -q` 284 passed, 2 skipped, 1 failed (only the Bedrock test); not tried against real Bedrock.
- **Files:** `backend/src/cascadasen/api/{assistant_routes,app,limits}.py`, `backend/tests/integration/test_assistant_api.py`.

## 2026-11-21 · feat(assistant): chat use case with step and deadline caps

- **Changed:** `application/assistant.py`: `Assistant.chat(message, conversation_id, session_id, toolbox_for)` runs a tool-use loop (max `assistant_max_steps`, deadline `assistant_deadline_s`), trims big tool results to 8 KB, keeps the history trimmed at a user turn, and stores each conversation as `assistant/<cid>.json` in the `DocumentStore` (conditional writes; a lost race raises `ConversationConflictError`). `domain/ports.py` adds the `ToolBox` port; `mcp/toolbox.py` (`SessionTools`) implements it over `Sub50Tools`: it drops `end_session`, caps `step` at 24 cycles, and turns every failure into `(False, {"error"})` for the model.
- **Why:** The use case depends only on ports, so the provider and the tool wiring stay in adapters. A model failure keeps the user's turn and a placeholder assistant turn, so roles keep alternating on retry. `truncated` is `"steps"` or `"deadline"`; the next message ("continúa") resumes from the stored history.
- **Agents:** `session_id` and `run_id` live in the conversation document, so any instance continues a conversation. The conversation id is a capability like the session id. Not wired to HTTP yet.
- **Files:** `backend/src/cascadasen/{application/assistant.py,mcp/toolbox.py,domain/ports.py}`, `backend/tests/unit/test_assistant.py`.

## 2026-11-21 · feat(assistant): tool schemas and in-process transport over the MCP tools

- **Changed:** `mcp/specs.py` builds JSON Schemas from the signatures of `Sub50Tools` (no `title`, `T | None` collapsed, defaults dropped) for an LLM that calls tools directly. `infrastructure/inprocess.py` adds `InProcessTransport` and `in_process_client(app, client_ip)`: an httpx client that enters the same FastAPI app through ASGI from a worker thread, presenting the caller's IP as the peer. `INSTRUCTIONS` moved from `mcp/server.py` to `mcp/tools.py` (the assistant imports it without the optional `mcp` SDK; `server.py` still exposes it).
- **Changed:** `httpx` is now a main dependency (`mcp/client.py` runs in production); the `mcp` extra holds only `mcp>=2.0`. `uv.lock` updated.
- **Why:** The in-app assistant reuses the MCP tools through the real routes, so validation, errors and per-IP rate limits all apply without a network hop or a loopback port shared by every user.
- **Agents:** `in_process_client` must be used from a sync (`def`) route or a thread, because it calls `anyio.from_thread.run`. It sends `Accept-Encoding: identity` so the GZip middleware does not compress the internal bodies.
- **Files:** `backend/src/cascadasen/{mcp/specs.py,mcp/tools.py,mcp/server.py,infrastructure/inprocess.py}`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/unit/test_tool_specs.py`.

## 2026-11-21 · feat(assistant): tool-chat port and Bedrock Converse adapter

- **Changed:** `domain/ports.py` gets `ToolSpec`, `ToolCall`, `AssistantTurn`, `ToolChatError` and the `ToolChatModel` port (provider-neutral messages: `user`, `assistant` with `tool_calls`, `tool` with `tool_call_id`, `ok`, `result`). `infrastructure/llm_tools.py` implements it for Bedrock Converse (`ConverseToolChat`, `tool_chat(settings)`); it reuses `make_client` and returns `None` unless `CASCADASEN_LLM_ENABLED` and `CASCADASEN_LLM_PROVIDER=bedrock-converse`. New settings `assistant_max_steps`, `assistant_deadline_s`, `assistant_call_timeout_s`, `assistant_history_messages`, `rate_assistant_per_minute`.
- **Why:** First step of the in-app natural-language assistant (user decision: bedrock-converse only, JSON response with the tool trace). The port keeps `application/` free of any provider.
- **Agents:** Errors from Bedrock become `ToolChatError` with a fixed Spanish message and no provider detail. Nothing is wired to the API yet.
- **Files:** `backend/src/cascadasen/{domain/ports.py,infrastructure/llm_tools.py,infrastructure/settings.py}`, `backend/tests/unit/test_llm_tools.py`.

## 2026-11-21 · docs(mcp): guide for the MCP server and links from the agent docs

- **Changed:** New `docs/mcp.md` (run, layout, tools, guardrails, how to add a tool). `docs/openapi.md`, `docs/stack.md` and `docs/agents.md` now point to it instead of saying the MCP server is future; `backend/README.md` has the run and `claude mcp add` commands; `AGENTS.md` section 1 lists `docs/mcp.md` in the read order.
- **Why:** The server exists, so the older "will wrap them" wording was wrong.
- **Agents:** Read `docs/mcp.md` before touching `cascadasen/mcp/`.
- **Files:** `docs/{mcp,openapi,stack,agents}.md`, `backend/README.md`, `AGENTS.md`.

## 2026-11-21 · feat(mcp): MCP server with 23 curated tools over the agent API

- **Changed:** New package `cascadasen/mcp/` (client, state, digest, tools, server). Tools: session (`start_session`, `join_session`, `end_session`, `list_options`, `describe_network`), network edits (`add_datacenter`, `add_generator`, `add_line`, `add_bus`, `edit_element`, `remove_element`, `reset_network`), sandbox (`cut_lines`, `repair_lines`, `get_grid_state`) and runs (`start_run`, `inject_event`, `step`, `submit_action`, `run_status`, `run_report`, `after_action`, `replay`). Results are compact summaries with the scenario `notice`.
- **Why:** Simulations driven only by natural language. User decisions: only the MCP server (the LLM lives in the client), stdio transport calling the API over HTTP (`SUB50_API_URL`), curated tools instead of 1:1 with the OpenAPI.
- **Agents:** No API route changed, so the agent spec is not regenerated. Edits send no `If-Match` (operations do not overwrite each other); a 409 is retried once. No tool ranks or searches cuts (`cyber.md` section 8): a test guards the tool names and another checks each tool's operationIds against `docs/openapi/agents.openapi.json`. Not done: remote HTTP transport and API authentication. Verification: `uv run --extra mcp pytest -q` 258 passed, 2 skipped, 1 failed (only the Bedrock test); smoke test on the real 188-bus API.
- **Files:** `backend/src/cascadasen/mcp/*`, `backend/tests/{unit/test_mcp_tools.py,integration/test_mcp_server.py}`.

## 2026-11-21 · build(mcp): optional mcp extra and cascadasen-mcp entry point

- **Changed:** `pyproject.toml` gets the optional extra `mcp = ["mcp>=2.0", "httpx>=0.28"]` and the script `cascadasen-mcp = "cascadasen.mcp.server:main"`; `uv.lock` is updated.
- **Why:** The MCP server (next commit) needs the SDK and `httpx` at runtime, and `httpx` was dev-only. The SDK is `mcp` 2.x, where `FastMCP` became `mcp.server.mcpserver.MCPServer`.
- **Agents:** Install with `uv sync --extra mcp`. The script exists only once the `cascadasen.mcp` package lands in the next commit.
- **Files:** `backend/pyproject.toml`, `backend/uv.lock`.

## 2026-11-21 · fix(api): trusted client IP, rate-limit global runs, document the version tag

- **Changed:** `limits.client_ip` takes the `X-Forwarded-For` entry `CASCADASEN_TRUSTED_PROXY_HOPS` from the right (new setting `trusted_proxy_hops`, default 0 = peer address); `infrastructure/ecs.tf` sets it to 2 (CloudFront appends the viewer, the ALB appends CloudFront). The leftmost entry, which a client can set, is ignored.
- **Changed:** `POST /api/v1/sim/runs`, `/events`, `/step` and `/replay` are limited to `rate_writes_per_minute` (60) per client IP (429 with `Retry-After`, declared in the agent spec) and `BodyLimitMiddleware` covers `/api/v1/sim/runs` as well as `/api/v1/sessions` (`BODY_LIMIT_PREFIXES`).
- **Changed:** `docs/infrastructure.md` and a comment in `ecs.tf` say `CASCADASEN_VERSION` is the image tag of the last `terraform apply` (CI swaps images on a copy of the task definition), so run records' `code_version` is informational.
- **Why:** Review findings 5, 6 and 9: rotating `X-Forwarded-For` bypassed the session-create limit and the SSE slots; every global run command is an S3 PUT in production with no limit or body cap; the version note was missing.
- **Agents:** Behind any other proxy chain set `CASCADASEN_TRUSTED_PROXY_HOPS` to the number of proxies that append to `X-Forwarded-For`. Nothing was applied to AWS; the env var lands with the pending sessions apply. Verification: `uv run pytest -q` 244 passed, 2 skipped, 1 failed (only the Bedrock test); `terraform -chdir=infrastructure fmt -check -recursive` and `validate` ok; lint clean; agent spec regenerated.
- **Files:** `backend/src/cascadasen/api/{limits,simulation_routes}.py`, `backend/src/cascadasen/infrastructure/settings.py`, `backend/tests/integration/test_sessions_api.py`, `infrastructure/ecs.tf`, `docs/openapi/agents.openapi.json`, `docs/{infrastructure,sessions-api,stack}.md`.

## 2026-11-21 · fix(sessions): separate dataset revision, document uncapped external actions

- **Changed:** Session documents carry `dataset_revision` next to `revision` (also in `last_op`, SSE events, `/network`, `/state`, edit and cut/repair responses). Edits, reset, cut and repair bump both; `run_created`/`run_updated` bump only `revision`. `If-Match` is checked against `dataset_revision`; `/network`, `/state`, edits, reset, cut and repair send `ETag: "<dataset_revision>"`; `GET /{sid}` and run commands keep `ETag: "<revision>"`. The network view and the session world are cached by `(sid, dataset_revision)`. A `run_updated` index write that loses its retries no longer turns a persisted step into 409.
- **Changed:** Web: edits send `If-Match` with `network.dataset_revision`; an event whose `dataset_revision` equals the one on screen refetches only `GET /{sid}`; the bar shows `session.revision`.
- **Changed:** External run actions stay uncapped (behaviour unchanged): `docs/sessions-api.md` 5, `docs/agents.md` 2.4 and the `submit_run_action` description now say they skip C2's operator attention cap, its conflict rules and vetoes (they still spend one attention unit and go through validator, resources and crews). New test `test_external_actions_are_not_capped_by_operator_attention`. New SSE test that edits from a second client while the stream is open and gets the second `revision` event.
- **Why:** Review findings 3, 4 and 10: an agent stepping a run caused 412s for editors and three refetches plus a baseline recompute per client per step; the docs claimed attention checks that the code does not apply; only the first SSE event was tested.
- **Agents:** Clients that used `revision` for `If-Match` must use `dataset_revision` (the ETag of `/network` or of the last edit). The FEAT entries below that say "every mutation bumps the revision used by If-Match" or "every revision refetches" are superseded. Capping external actions by attention is an open product decision, not implemented. Verification: `uv run pytest -q` 242 passed, 2 skipped, 1 failed (only the Bedrock test); `npx vitest run` 22 passed; `npm run build` ok; lint clean; agent spec regenerated.
- **Files:** `backend/src/cascadasen/application/sessions.py`, `backend/src/cascadasen/api/session_routes.py`, `backend/tests/{unit/test_sessions.py,unit/test_run_actions.py,integration/test_sessions_api.py}`, `web/src/session/{useSession.ts,sessionApi.ts,SessionBar.tsx}`, `web/src/cascade/{types.ts,CascadeApp.tsx}`, `docs/openapi/agents.openapi.json`, `docs/{sessions-api,agents,stack,mapa3}.md`.

## 2026-11-21 · fix(sessions): rebalance out-of-service buses and bound bus overrides

- **Changed:** `overlay._rebalance`: the lost base injection of an out-of-service bus (or a group of adjacent ones) is redispatched in the single live island its in-service base lines touched; when they touched several islands the outage split them and each part keeps its base imbalance (`unbalanced_island`). Out-of-service islands get no warnings. Buses whose `gen_mw`/`sync_mw` the overlay sets take no share of the redispatch (toy: B000 at 600 MW stays at 600).
- **Changed:** Bus overrides are bounded: `load_mw`, `gen_mw`, `sync_mw` ≤ base value + 3000 MW, `inertia_mws` ≤ 10 s × `sync_mw`; the absolute `load_mw` and `gen_mw` change counts toward the 5000 MW budget. `BusPatch` adds a coarse `le=20000` (MW) guard.
- **Why:** Review findings 1, 2 and 7: taking a bus out of service left the base case off-balance (toy B001: 51.4 Hz), while `load_mw=0` was rebalanced; `load_mw=1e9` was accepted; a generation edit was partly undone by its own redispatch. User decision 2 and "the system must stay correct".
- **Agents:** The FEAT entry `feat(sessions): session overlay…` below is wrong where it says an out-of-service base bus leaves its island unbalanced. On the 188-bus network, B010, B050 or B100 out of service leave gen − load at −0.03 MW (base rounding); B100 still sheds 639 MW in the baseline from line overloads (the rule is not an OPF). Contract: `docs/stack.md` 6.2, `docs/sessions-api.md` sections 8 and 10. Verification: `uv run pytest -q` 237 passed, 2 skipped, 1 failed (only the Bedrock test); lint clean; agent spec regenerated.
- **Files:** `backend/src/cascadasen/domain/cascade/overlay.py`, `backend/src/cascadasen/api/session_schemas.py`, `backend/tests/unit/test_overlay.py`, `docs/openapi/agents.openapi.json`, `docs/{stack,sessions-api}.md`.

## 2026-11-21 · chore(api): regenerate the agent OpenAPI spec with session routes

- **Changed:** After merging `main` (`92256c6`), `session_routes.py` imports `AGENT` and `errors()` from `api/agent_openapi.py`; the duplicate `ErrorResponse` in `api/schemas.py` is gone. `docs/openapi/agents.openapi.json` regenerated: it now holds every session route except the SSE stream. The spec description and the `global_create_run` description say runs are persisted 24 h and rebuilt from the recipe (was "live in server memory, the most recent 100"). `test_request_bodies_describe_every_field` follows `$ref`s inside `anyOf`, because `POST /sessions` takes an optional body.
- **Why:** Plan "Final rebase" step and review finding 8: one `ErrorResponse`, a spec in sync with the app, and references to the committed conventions instead of the untracked `.agents/tasks/openapi-agent-conventions.md`.
- **Agents:** The conventions are in `docs/openapi.md`; `session_routes.py`, `docs/sessions-api.md` and `docs/stack.md` 7.2 point there. Regenerate the spec with `cd backend && uv run python -m cascadasen.api.agent_openapi` whenever a session route or its models change. Global `/sim/runs*` stay marked; unmarking them is an open decision. Verification: `uv run pytest -q` 230 passed, 2 skipped, 1 failed (only the known Bedrock test).
- **Files:** `backend/src/cascadasen/api/{session_routes,schemas,agent_openapi,simulation_routes}.py`, `backend/tests/integration/test_agent_openapi.py`, `docs/openapi/agents.openapi.json`, `docs/{sessions-api,stack}.md`.

## 2026-11-21 · docs(sessions): correct the production /api note in mapa3

- **Changed:** `docs/mapa3.md` section 11 no longer says the deployed site has no backend behind `/api`. CloudFront and the ALB already route `/api/*` to the backend; until the sessions bucket and task role are applied, the deployed backend keeps sessions in memory (`CASCADASEN_SESSION_STORE` defaults to `memory`) and loses them on restart or deploy.
- **Why:** Cross-FEAT integration check of feat/shared-sessions: the web doc (FEAT web) contradicted the infra routing in `docs/infrastructure.md` and `infrastructure/alb.tf` (FEAT infra).
- **Agents:** The note "The deployed static site has no `/api` behind it yet" in the `feat(web): session mode for mapa 3` entry below is wrong; this entry supersedes it. Integration checks on this branch: backend pytest (only the known Bedrock test fails), web vitest + build, lint on all changed files and terraform fmt/validate all pass. `main` gained `92256c6` (agent OpenAPI spec) after this branch forked and the two conflict; the merge step must follow the plan's "Final rebase" steps.
- **Files:** `docs/mapa3.md`.

## 2026-11-21 · feat(infra): sessions S3 bucket and ECS task role (validated, not applied)

- **Changed:** New `infrastructure/s3.tf`: bucket `cascadasen-sessions-402909940511` with public access block, SSE `AES256`, `BucketOwnerEnforced` and lifecycle rules on `sessions/` and `runs/` (expire after `var.session_ttl_days`, default 1; abort multipart after 1 day). `iam.tf`: role `cascadasen-task` with inline policy `cascadasen-task-sessions` (Get/Put/Delete on `sessions/*` and `runs/*`, ListBucket on the bucket). `ecs.tf`: `task_role_arn` and backend-only env `CASCADASEN_SESSION_STORE=s3`, `CASCADASEN_SESSION_BUCKET`, `CASCADASEN_AWS_REGION`, `CASCADASEN_VERSION=var.image_tag`. Output `sessions_bucket`; `deploy-role-policy.json` PassRole adds `cascadasen-task`.
- **Why:** Shared-sessions plan item 10: production sessions and runs must survive restarts and be shared across instances (user requests 3-4).
- **Agents:** Nothing was applied; the apply waits until the user tests sessions locally. After the apply, run once `aws ecs update-service --cluster cascadasen --service cascadasen --task-definition cascadasen:<revision registered by terraform>` (the service ignores `task_definition` and CI copies the current revision) and re-attach `deploy-role-policy.json` to `IAM-Role-ECS-Deploy`. `docs/infrastructure.md` section "Sessions bucket" is the reference. Validation: `terraform -chdir=infrastructure init -backend=false -input=false`, `fmt -check -recursive`, `validate`.
- **Files:** `infrastructure/{s3,iam,ecs,variables,outputs}.tf`, `infrastructure/deploy-role-policy.json`, `docs/infrastructure.md`.

## 2026-11-21 · feat(web): session mode for mapa 3 with a Datos tab and the dev /api proxy

- **Changed:** New `web/src/session/`: `sessionApi.ts` (typed calls for every `/api/v1/sessions` route, `ApiError`, `sessionIdFrom`, `subscribe` with SSE and a 2 s `If-None-Match` polling fallback), `useSession.ts`, `SessionBar.tsx` (Crear sesión, Unirse, Copiar enlace, Salir, rev. N, en vivo/sondeo), `DataPanel.tsx` (tab **Datos**: Barras, Líneas, Generadores, Cargas y datacenters with add/patch/service/delete, origin badges, "supuesto (sesión)", baseline, balance, warnings, Restablecer, map pick, nearest ≥220 kV bus) and `geo.ts`. `CascadeApp.tsx`: with `?sesion=` the network, buses and timeline come from the session (`/network`, `/state`), a line click calls `/cut`, Simulación lists open lines with Reparar/Reparar todo, the point pill is pinned, every revision refetches. `vite.config.ts` proxies `/api` to `VITE_API_TARGET` (default `http://localhost:8000`); compose sets `VITE_API_TARGET=http://backend:8000` and `depends_on: backend`.
- **Why:** Shared-sessions plan items 8 and 9: a user creates or joins a session in the browser, edits its copy of the dataset, and sees other clients' edits live (user requests 2-3).
- **Agents:** Without `?sesion=` (and no `sub50_session` in localStorage) the app makes no `/api` request and works with the backend stopped; a stored id re-enters session mode, a 404 forgets it, a connection error falls back to the cache with a message. UI edits send `If-Match` with the revision on screen (412 reloads and asks to retry) and `X-Sub50-Agent: web`. The deployed static site has no `/api` behind it yet. Local E2E (compose, file store, through the web proxy): the SSE revision event reached client B 1.0 s after client A's POST; after `docker compose restart backend` the session (revision 3: the load plus `run_created` and `run_updated`) and its run (cycle 3, `rebuilt: true`, `trace_matches: true`, same trace head) were intact; with `backend` stopped `/`, `/cache/index.json` and the cut cache still load. 22 web tests (14 before).
- **Files:** `web/src/session/*`, `web/src/cascade/{CascadeApp.tsx,types.ts}`, `web/src/styles.css`, `web/vite.config.ts`, `docker-compose.yml`, `web/README.md`, `docs/{mapa3,docker,architecture}.md`.

## 2026-11-21 · docs(sessions): agent guide for the sessions API

- **Changed:** New `docs/sessions-api.md` (session concept and the four points, create/join, the rule that every agent endpoint takes `{sid}` in the path, endpoint table with operationIds and codes, curl examples for datacenter/bus/line/generator CRUD, cut, repair, runs, run actions, replay and trace, SSE format and reconnection, polling fallback, ETag/If-Match, limits, 24 h TTL and S3 rounding, error codes, physics rules, notice and guardrails). Linked from `AGENTS.md` section 1 (read-order item 9), `docs/stack.md` new 7.2 "Sessions API" and `docs/agents.md` new 2.4 "External agents". `docs/architecture.md` 2.5 lists `session_routes.py`, `limits.py`, `session_schemas.py`; new 3.3 "A session edit and its live update". `docs/plan.md` section 9 item 14 records the user decisions. Fixed the `ActionIn.target` example (theatre corridors are `A06-A07`, no voltage suffix).
- **Why:** Shared-sessions plan item 7: agents on other machines must know to pass the session id to every call (user request 5).
- **Agents:** Every curl path in `docs/sessions-api.md` matches a route of `create_app().openapi()["paths"]`, and the examples were run in order against the real 188-bus world (all 2xx, the queued `restore_element` executed on `A06-A07`, trace verified). External run actions skip C2's choice and vetoes; they are re-validated and spend attention, resources and crews when executed. Update the guide when a session route changes.
- **Files:** `docs/sessions-api.md`, `AGENTS.md`, `docs/{stack,agents,architecture,plan}.md`, `backend/src/cascadasen/api/session_schemas.py`.

## 2026-11-21 · feat(api): sessions HTTP API with limits and SSE

- **Changed:** New router `api/session_routes.py` under `/api/v1/sessions`: session create/get (ETag, `If-None-Match` → 304)/delete/reset, `GET /{sid}/network`, POST/PATCH/DELETE for `buses`, `lines`, `loads`, `generators` (`/{sid}/<plural>[/{element_id}]`), sandbox `cut`/`repair`/`state`, nested runs (`/{sid}/runs`, `/{sid}/runs/{rid}` + `events`, `step`, `actions`, `replay`, `snapshots`, `trace`, `report`, `after_action`) and the SSE stream `GET /{sid}/events`. New `api/session_schemas.py` (request models, `extra="forbid"`), `api/limits.py` (`TokenBucket`, `SseSlots`, `client_ip`, `BodyLimitMiddleware` 413 over 64 KB on `/api/v1/sessions*`), `ErrorResponse` in `api/schemas.py`. `create_app(..., sessions=)`, CORS allows PATCH/DELETE and exposes `ETag`; `/admin/reload` also drops the session service.
- **Why:** Shared-sessions plan item 6: agents and browsers on other machines create and edit a session and see each other's changes live (user requests 3-5).
- **Agents:** Every session route except `GET /{sid}/events` carries `x-sub50-agent`, an operationId from `.agents/tasks/openapi-agent-conventions.md`, English summary/description, tags `sessions|session-network|session-sandbox|session-runs` and `ErrorResponse` on its 4xx codes (422 is declared on every route, replacing FastAPI's `HTTPValidationError`); `test_sessions_api.py` asserts it. `ErrorResponse.detail` is `str | dict | list` (input errors are `{field, message, valid}`, validation errors a list), the same widening the parallel openapi-agent-spec branch made; keep one definition when merging (theirs lives in `api/agent_openapi.py`). Mutations read `If-Match: "<revision>"` (412 on mismatch or a non-integer) and `X-Sub50-Agent` (≤64 chars, default `anon`) and answer with `ETag`. Rate limits are per process: create per client IP (`rate_create_per_hour`), cut/repair per sid (`rate_cuts_per_minute`), other writes and run commands per sid (`rate_writes_per_minute`); 429 has `Retry-After`. SSE: first event has `retry: 2000`, then `id/event: revision/data {type, revision, op, ids, by}` on change, `: ping` every `sse_heartbeat_s`, store head every `sse_head_s`, closes after `sse_max_s`; the server ignores `Last-Event-ID` and always starts with the current revision. The body limit trusts `Content-Length` only. `POST /{sid}/repair` with neither `lines` nor `all` gives 422. Element path parameter is `element_id`. No `GET /{sid}/runs` list (the session document has `runs`). The agent spec endpoint and its snapshot file are not built here.
- **Files:** `backend/src/cascadasen/api/{session_routes,session_schemas,limits,schemas,app}.py`, `backend/tests/integration/test_sessions_api.py`.

## 2026-11-21 · feat(sessions): session overlay, SessionWorld and SessionService use cases

- **Changed:** New `domain/cascade/overlay.py`: `empty_overlay`, `add`/`patch`/`remove(overlay, kind, …, net, point)` and `apply_overlay(net, point, overlay) -> Applied(net, point, warnings, balance)` over the 188-bus network (added buses `B###`, lines `U###`, loads/datacenters `D###`, generators `G###`, base overrides, `in_service: false`, session-bus tombstones), with bounds and a per-island proportional synchronous redispatch (`is_assumption`). New `SessionWorld` in `application/theater_world.py` (one pinned point + overlay, a `TheaterWorld`). `SimulationService.theater_network` now calls the module function `theater_network_view(net, op, point, points)` (output unchanged). New `application/sessions.py` `SessionService`: create/get/delete, `mutate` with revision, `if_revision` (412) and 3 retries on store conflicts, `add`/`patch`/`remove`/`reset`, `network_view` (origin, overrides, out of service, warnings, balance, baseline; LRU by `(sid, revision)`), sandbox `cut`/`repair`/`state`, nested runs (`create_run`, `run_command`, at most 20 per session), `revision`/`head` for SSE.
- **Why:** Shared-sessions plan items 4 and 5: each session edits its own copy of the dataset, stored as one JSON document, while runs keep the dataset they were created with (user decisions 1, 3, 6).
- **Agents:** Contract in `docs/stack.md` 6.2. Deviations from the plan: `overlay.add/patch/remove` also take the base `point` (validation needs it); `balance[].buses` is a dict `bus id -> MW`; the view adds `loads`, `generators` and `in_service` on nodes; documents carry `share_path` and `expires_at` in `get`/`create` output. Errors: `SessionNotFoundError` (also for a malformed sid), `PreconditionFailedError`, `SessionLimitError`, `ConflictError` after retries, `OverlayError(field, message, valid, not_found, conflict)`. `run_command(sid, rid, name, *args, by=…, **kwargs)` for `state, inject, step, action, replay, snapshots, trace, report, after_action`; mutating ones bump the session revision (`run_updated`/`run_created`) and return `session_revision`. Taking a base bus out of service leaves its island unbalanced by the bus's base injection (reported as `unbalanced_island`). On the real network a 300 MW datacenter at `B010` overloads 14 lines in the baseline (373 MW shed): the rule is not an OPF. No HTTP routes yet.
- **Files:** `backend/src/cascadasen/domain/cascade/overlay.py`, `backend/src/cascadasen/application/{sessions,theater_world,simulation_service}.py`, `backend/tests/unit/{test_overlay,test_sessions}.py`, `docs/stack.md`, `docs/architecture.md`.

## 2026-11-21 · feat(runs): persist strategic runs, accept external actions, gate admin reload
- **Changed:** `RunManager` persists every command as `runs/<run_id>.json` (`{run_id, recipe, cycle, trace_head, code_version, created_at, updated_at, extra}`, conditional write on the last etag) and keeps live simulations in a process-wide `RunCache` (LRU, `CASCADASEN_RUN_CACHE_SIZE=20`, 64 striped locks). A run missing from the cache is rebuilt from its record and reports `rebuilt` and `trace_matches`. `Simulation.submit_action` (and `RunManager.action`) queues an external agent COA: structure checked now (`RunInputError` on action, role, target), executed next cycle as `Decision(coa, True, "external_agent", …)` unless C2 approved the same key, re-validated like any proposal. `RunConfig.from_dict`; `recipe()` adds `cycle` and `actions`. `POST /api/v1/admin/reload` answers 404 unless `CASCADASEN_ADMIN_ENABLED=true`; docker compose sets it and `CASCADASEN_SESSION_STORE=file`.
- **Why:** Runs only lived in one process's memory, so they were lost on restart and invisible to other instances, and memory grew with every run (shared-sessions plan items 2 and 3; user decisions 7, 9, 14).
- **Agents:** Run ids must match `^[0-9a-f]{12}$` or the API gives 404 before touching the store. `RunConflictError` → 409 "La corrida cambió en otra instancia; reintenta" (the stale copy is evicted, a retry rebuilds). `RunManager(world, physics, *, store, prefix="runs/", cache, world_for, extra, version, clock)`; `SimulationService(..., store, run_cache, version)` exposes `.store` and `.run_cache`; `create_app(..., store=)` sets `app.state.settings` and `app.state.store` (defaults to the injected `SimulationService`'s store, else `container.document_store(settings)`). Action records carry `after_events` (events injected before it) so a rebuild keeps the input order. Trace heads of runs without actions are unchanged (checked against `main`). LLM-commander runs report `trace_matches: false` after a rebuild. A cached run is not re-checked against the store on reads: with several instances a read can be stale until the next command conflicts. `application/run_experiment.py` imports `MemoryDocumentStore` lazily when no store is given. The git pre-commit hook uses `mapfile` and fails on macOS `/bin/bash` 3.2.
- **Files:** `backend/src/cascadasen/domain/theater/cycle.py`, `backend/src/cascadasen/application/{run_experiment,simulation_service}.py`, `backend/src/cascadasen/api/{app,simulation_routes,simulation_schemas}.py`, `backend/tests/unit/{test_run_actions,test_run_persistence}.py`, `backend/tests/integration/{test_runs_api,test_api}.py`, `docker-compose.yml`, `docs/{architecture,stack,docker}.md`, `backend/README.md`.

## 2026-11-21 · feat(store): document store port with memory, file and S3 adapters
- **Changed:** `domain/ports.py` gains `ConflictError` and the `DocumentStore` Protocol (`get` → `(doc, etag) | None`, `put(key, doc, if_match=, if_none_match=)` → etag, `head`, `delete`). New `infrastructure/document_store.py` with `MemoryDocumentStore`, `FileDocumentStore` and `S3DocumentStore`; `container.document_store(settings)` picks one. `Settings` adds `session_store`, `session_bucket`, `session_dir` (property `sessions_dir`), `session_ttl_hours` (24), `run_cache_size` (20), `admin_enabled` (false), `version`, and the rate and SSE knobs used by later session work. `boto3>=1.40` is a main dependency.
- **Why:** Runs and sessions must survive restarts and be shared across instances (shared-sessions plan item 1).
- **Agents:** Keys are `runs/<run_id>.json`, `sessions/<sid>.json` and `sessions/<sid>/runs/<rid>.json`. Memory and file stores take `ttl_s` and a `clock`; the file store stamps mtime with its clock and raises `ValueError` on keys with `..`, a leading `/` or a backslash. S3 `PreconditionFailed`/`ConditionalRequestConflict`/412/409 → `ConflictError`, `NoSuchKey`/404 → `None` (a 404 on an `if_match` put is also a conflict). `data/sessions/` is git-ignored. Nothing uses the store yet; the rate and SSE settings are unused until the session API lands.
- **Files:** `backend/src/cascadasen/domain/ports.py`, `backend/src/cascadasen/infrastructure/{document_store,settings,container}.py`, `backend/tests/unit/test_document_store.py`, `backend/pyproject.toml`, `backend/uv.lock`, `.gitignore`, `docs/architecture.md`.
## 2026-11-21 · feat(api): agent-only OpenAPI spec for external agents

- **Changed:** New `api/agent_openapi.py`: `AGENT` marker (`openapi_extra={"x-sub50-agent": True}`), shared `ErrorResponse {detail}` with `errors({code: text})`, and a spec built from the marked routes, served at `GET /api/v1/agents/openapi.json` with a Swagger page at `/api/v1/agents/docs`. Marked and documented in English (operationId, summary, description, error responses, param and body field descriptions with examples): `/sim/catalog` (`get_catalog`, tag `catalog`), `/sim/network` (`global_get_network`) and every `/sim/runs*` route (`global_*`, tag `global-runs`).
- **Changed:** Versioned `docs/openapi/agents.openapi.json` and `tests/integration/test_agent_openapi.py` (exact marked set, unique snake_case ids, text, ErrorResponse on 4xx, body field descriptions, committed file equals the app's spec, served route, full `/openapi.json` unchanged). No endpoint behaviour changed.
- **Why:** Agents (and a later MCP wrapper) need a small public spec with only the CRUD, run and catalog endpoints, separate from the full `/docs`.
- **Agents:** Follow `docs/openapi.md` for every agent route: mark it, set `operation_id` from its list, English summary/description, `responses=errors(...)`, tags. Regenerate with `cd backend && uv run python -m cascadasen.api.agent_openapi` in the same commit, or the test fails. Session routes (`/sessions/*`) still need marking when they land. Tags and English summaries of the marked routes also changed in the full `/docs` (were `experimentos`, Spanish). `ErrorResponse.detail` is `str | object | list` because simulator input errors return `{field, message, valid}`.
- **Files:** `backend/src/cascadasen/api/{agent_openapi,app,simulation_routes,simulation_schemas}.py`, `backend/tests/integration/test_agent_openapi.py`, `docs/openapi.md`, `docs/openapi/agents.openapi.json`, `docs/{stack,architecture,agents}.md`, `backend/README.md`.
## 2026-11-21 · feat(web): click selects a line, double click cuts it

- **Changed:** A single click on a line or substation now selects it (white halo, card at the top of the panel in both tabs, no tab or colour switch); a double click on a line, or the card's "Sacar de servicio" button, cuts it; "Reponer línea" (line card and impact card) returns to the base case. A cut clears the selection so the impact card stays at the top. The line card shows voltage, model branches, capacity, flow with direction, loading bar and status at the current second, with info icons. Built on the Design v6 rail and colours (entry below): the conditions tree already keeps the cut across hours; if a cut's timeline is missing at the chosen condition the app now falls back to the base case with a note. The event history scrolls inside its own card (it used to scroll the whole panel), a new selection scrolls the panel back to the top, and the map tooltip sits beside the pointer and flips near the right and bottom edges. Plain-language result when a cut leaves nobody without supply, a hint in the timeline with no cut, loading cards, pointer cursor over clickable map elements, Space play/pause, Escape (closes the layers panel, else clears the selection), outside click closes the layers panel, "Ver todo Chile" control, focus-visible outlines.
- **Why:** The owner clicked lines to see their details and cut them by accident; the other items are the UX problems found in the same pass.
- **Agents:** Click interpretation is the pure `interpretClick` in `web/src/cascade/clicks.ts` (tests in `clicks.test.ts`). Mapbox delivers a double click as three callbacks (click tapCount 1, click tapCount 1, dblclick forwarded as click tapCount 2: `@deck.gl/mapbox` `dist/mapbox-overlay.js` `_handleMouseEvent`); the offline `Deck` has `doubleClickZoom: false`, so clicks fire at once with tapCount 1, 2 (`@deck.gl/core` `dist/lib/constants.js` RECOGNIZERS, `mjolnir.js` tap recognizer). On Mapbox a dblclick on a clickable element is `preventDefault`ed so it does not zoom; on touch screens Mapbox double-click zoom is disabled. `Handlers` in `web/src/map/baseMap.ts` now needs `isClickable`, `onClick` gets `tapCount`, and `BaseMap` has `fitAll()`. `lineStateAt` treats a line at exactly 100 % as "en servicio, al límite": the engine flags base-case lines at their limit as `overload` with loading 1.0. Checked in a browser on 2026-11-21: on Mapbox a double click cuts once and does not zoom (empty map still zooms), and a double tap cuts once on both basemaps.
- **Files:** `web/src/cascade/clicks.ts`, `clicks.test.ts`, `SelectionCard.tsx`, `CascadeApp.tsx`, `NetworkPanel.tsx`, `SimulationPanel.tsx`, `Timeline.tsx`, `Legend.tsx`, `layers.ts`, `simulation.ts`, `simulation.test.ts`, `cascade.css`, `web/src/map/baseMap.ts`, `docs/mapa3.md`, `web/README.md`.

## 2026-11-21 · feat(regional): draw the other countries' lines like Chile's

- **Changed:** Regional lines now use Chile's `VOLTAGE_TIERS` colours and widths at full opacity instead of the old atlas `kvColor` palette (yellow and orange) dimmed to alpha 130. Regional substations use Chile's node style (`NODE_COLOR`, radius 3 at 500 kV, 2 below). In the Simulación (load) view regional lines turn neutral gray `#767B80` (`REGIONAL_NO_LOAD`), because they have no load and green would claim "< 50 %". The help legend text and swatch follow.
- **Why:** Ignacio asked for the lines outside Chile to follow the design (`design.md` section 3, Design v6 tokens) and look the same as Chile's. Closes the open item of the entry below: the regional `KV_COLORS` read like load colors next to Chile.
- **Agents:** `buildRegionalLayers(grid, colorMode)` now takes the colour mode; `CascadeApp` rebuilds the regional layers when it changes. `hex` is exported from `web/src/cascade/layers.ts`. Regional lines have no `autoHighlight` on purpose: clicking them does not cut. Regional plants keep the old `TECH_COLORS` discs (Chile's map draws no plants). `kvColor` and `KV_COLORS` in `web/src/map/layers.ts` are now only used by the old `/map` page.
- **Files:** `web/src/map/regional.ts`, `web/src/map/regional.test.ts`, `web/src/cascade/layers.ts`, `web/src/cascade/CascadeApp.tsx`, `web/src/cascade/Legend.tsx`, `docs/regional.md`, `docs/mapa3.md`, `CHANGELOG.md`.

## 2026-11-21 · feat(web): line colors with a logic and conditions in the nav rail

- **Changed:** Line colors in mapa 3 follow one rule: cold colors describe the network, the traffic-light ramp describes its stress, red is always failure. Voltage is white 500 kV, light cyan `#7FDBFF` 154-345 kV, blue `#3B9BF5` 100-110 kV, deep blue `#4F78E0` 44-69 kV. Load is green `#28B47E` under 50 %, yellow `#F5D547` 50-75 %, orange `#FF9838` 75-100 %, red over 100 %.
- **Changed:** The time pill over the map is removed. "Escenarios" in the nav rail is a two-level tree (new `Scenarios.tsx`): each scenario expands into the four operating conditions, and the active condition carries the selection.
- **Changed:** The dashed "fuera" lines are drawn above the live lines, so the cut line is no longer hidden under a parallel overloaded line.
- **Why:** Ignacio's review of the Paper mockup (page "Design v6"): the gray-to-red load ramp was too flat, the voltage hues had no logic, and the conditions belong under each scenario.
- **Agents:** `web/src/cascade/layers.ts` is still the single source for line colors; `networkSummary.ts` now derives `VOLTAGE_BANDS` from `VOLTAGE_TIERS`. A scenario is now a cut alone: "Apagón 25F" is cut `R239` at any point (it opens at `feb2025-1500` by default), so do not test for the 25F case with the point. `clock()` in `text.ts` returns only `hms` and `tenths`; `conditionName` and `conditionDate` format a point for the rail. The rules are in `docs/design.md` section 3.3. Open: the other countries' lines still use `KV_COLORS` from `web/src/map/layers.ts` (yellow and orange), which now read like load colors next to Chile. The draw order of "fuera" was not checked visually at close zoom.
- **Files:** `web/src/cascade/layers.ts`, `Scenarios.tsx`, `CascadeApp.tsx`, `cascade.css`, `MapLegend.tsx`, `Legend.tsx`, `networkSummary.ts`, `text.ts`, `text.test.ts`, `ui.tsx`, `docs/design.md`, `docs/mapa3.md`, `web/README.md`.

## 2026-11-21 · fix(web): draw the wordmark subscript with the logo's SVG paths

- **Changed:** The nav-rail wordmark draws its subscript "50" with the two paths of `web/public/favicon.svg` (Geist 800 "5" and the power button) instead of a Roboto "5" next to a hand-drawn 8 x 11 oval. Size and drop below the baseline are measured from `project-logo.png`.
- **Why:** Ignacio saw the "0" as stretched and the subscript at the wrong size; the old oval was taller than wide, while the logo's power button is nearly round.
- **Agents:** The ratios (5 = 0.69 "sub" x-heights tall, drop = 0.43 x-heights) are in `docs/design.md` section 6 and in the `.wordmark .subscript` rule. If the "sub" font size changes, rescale `width`, `height` and `vertical-align` together.
- **Files:** `web/src/cascade/ui.tsx`, `web/src/cascade/cascade.css`, `docs/design.md`.

## 2026-11-21 · docs(pitch): add pitch ideas and project benefits
- **Changed:** New `docs/pitch_idea.md`: pitch notes (25F losses of US$ 984 millones with source, "wow" moment ideas) and a "Beneficios de este proyecto" section with a short list of 17 benefits followed by a paragraph per benefit, including cost vs resilience trade-offs, best combination for a budget and minimum investment that avoids a national blackout.
- **Why:** The team needs material for the pitch.
- **Agents:** `docs/pitch_idea.md` is pitch material, in Spanish. Costs of the measures (e.g. US$ per MW of battery) are assumed values, not sourced data. The note in the doc says no user has been interviewed yet; do not turn the benefits into claims of validated demand.
- **Files:** `docs/pitch_idea.md`, `CHANGELOG.md`.
## 2026-11-21 · feat(regional): reduce the other countries' networks like Chile's

- **Changed:** New `domain/regional_reduction.py`: substations within 3 km become one bus, line ends are snapped to the nearest bus (12 km), OSM ways are chained, parallel lines are folded, small pieces dropped, and plants are added up per bus (40 km). `cascadasen-regional` now writes the reduced layer: lines `<ISO3>-R<n>` with `a`/`b` bus ids drawn straight, buses `<ISO3>-B<n>`, generation `<ISO3>-G<n>` per bus. Lines before to after: BRA 2,264 to 1,286, PER 575 to 246, BOL 244 to 58, ARG 3,056 to 390. The web reads the new fields; tooltips show circuits and plant counts.
- **Why:** Ricardo asked for the same reduction Chile has (`cascade/network.py`): one bus per substation, parallel lines folded, straight segments.
- **Agents:** The thresholds (3, 12, 40 km, 3 buses) are assumptions, constants at the top of `regional_reduction.py`. Plants far from every substation are dropped (BRA 15,581 MW, ARG 5,475 MW). The schema changed to v2: `source_record` is now `source_records`, plants carry `bus`, `mw_by_tech` and `count`. Regenerate with `uv run cascadasen-regional` (Argentina: `--countries ARG --osm ARG`). The reduced lines are not a simulable topology.
- **Files:** `backend/src/cascadasen/domain/regional_reduction.py`, `domain/regional.py`, `application/build_regional.py`, `backend/tests/unit/test_regional.py`, `backend/tests/validation/test_regional_data.py`, `data/processed/latam/`, `web/src/map/regional.ts`, `web/src/cascade/Legend.tsx`, `docs/regional.md`, `docs/stack.md`.

## 2026-11-21 · docs(regional): document the sources and the common schema

- **Changed:** New `docs/regional.md`: what is built, the common schema v1, the sources used with their status, and everything found and not used (region-wide datasets, Brazil ONS electrical parameters, Colombia XM API, Dominican Republic and Costa Rica ArcGIS services, Mexico CENACE, and the countries with nothing open). `datasets.md`, `architecture.md`, `stack.md` section 6.2, `idea.md` section 4 and `plan.md` section 9.14 point to it.
- **Why:** The research was exhaustive by request; the next agent should not repeat it.
- **Agents:** Status labels are verified / not verified / failed; only what was opened in this project is marked verified. Argentina's official source failed on 2026-11-21. Next candidates with verified sources: Dominican Republic, Costa Rica, Colombia (API only), Mexico (market data only).
- **Files:** `docs/regional.md`, `docs/datasets.md`, `docs/architecture.md`, `docs/stack.md`, `docs/idea.md`, `docs/plan.md`.

## 2026-11-21 · feat(web): draw the regional grid as a context layer

- **Changed:** New `web/src/map/regional.ts` loads `data/processed/latam/` (a glob, so the app builds without it) and draws dimmed lines by kV, substations and plants by technology under Chile's layers (`regional-*` ids). Tooltips show the source and "Red de contexto: no se simula". The legend lists countries, counts, licences and attribution. The offline map draws the neighbours' outlines and the camera limits reach Brazil.
- **Why:** Show the other Latin American grids in the same map without touching the Chile simulation.
- **Agents:** Regional layers are never clickable as a cut: click handlers only react to the ids `lines*`, `nodes`, `load`. After merging the Design v5 interface the regional legend block lives in `HelpPanel` (Ayuda) and the tooltip branch in `CascadeApp._tooltip`. The first view still frames Chile. `npx vitest run` covers the layers and tooltips.
- **Files:** `web/src/map/regional.ts`, `web/src/map/regional.test.ts`, `web/src/map/baseMap.ts`, `web/src/cascade/CascadeApp.tsx`, `web/src/cascade/layers.ts`, `web/src/cascade/Legend.tsx`.

## 2026-11-21 · feat(data): add regional grid exports and country outlines

- **Changed:** `data/processed/latam/` with lines, substations and plants for BRA (2,264 / 927 / 2,953), PER (575 / 269 / 246), BOL (244 / 71 / 31) and ARG from OpenStreetMap (3,056 / 308 / 208), a manifest, and `outlines.geojson` (geoBoundaries) built by `data/scripts/build_latam_outlines.sh`. New validation test `backend/tests/validation/test_regional_data.py`.
- **Why:** The web map reads these files; they are versioned like the rest of `data/processed/` so the demo needs no download.
- **Agents:** Argentina is the OSM fallback, not the official source; its 132 kV total looks high (duplicated circuits). Regenerate with `uv run cascadasen-regional` (add `--refresh` to download again). The validation test skips when the folder is missing.
- **Files:** `data/processed/latam/`, `data/scripts/build_latam_outlines.sh`, `backend/tests/validation/test_regional_data.py`.

## 2026-11-21 · feat(regional): add the regional grid model, adapters and command

- **Changed:** New pure `domain/regional.py` (common schema, voltage and technology normalisers, `normalise`, GeoJSON and manifest builders) and port `RegionalGridSource`. Four adapters in `infrastructure/sources/regional/` (EPE Brazil, Osinergmin Peru, Secretaría de Energía Argentina, OpenStreetMap through Overpass) and the command `cascadasen-regional --countries BRA,PER,ARG,BOL [--osm ARG] [--refresh]`.
- **Why:** Ricardo asked for other Latin American grids on the map in one common pattern. Decided with him: drawn only, no simulation; Brazil, Peru, Argentina, Bolivia.
- **Agents:** EPE gives power in kW and Osinergmin in MW (four records in kW, read above 3,000 as kW). The Argentina adapter was never run against the real files (server unreachable); it is tested only on a synthetic CSV, so fix its column candidates when the server answers. A failing country does not stop the others. Run tests with `uv run pytest`.
- **Files:** `backend/src/cascadasen/domain/regional.py`, `domain/ports.py`, `application/build_regional.py`, `infrastructure/sources/regional/`, `infrastructure/container.py`, `infrastructure/settings.py`, `backend/pyproject.toml`, `backend/tests/unit/test_regional.py`.

## 2026-11-21 · fix(web): a substation without supply is drawn red

- **Changed:** In mapa 3 a substation that loses supply (its island blacks out) is drawn as a red dot (`FAULT`, #FF5A48), a little bigger than a normal node and with a dark ring so it stands out on the gray lines. Before it was near-black (`DEAD_LINE`), which disappeared against the dark map. Lines between two dark substations keep the near-black "sin tensión" color. Code: the `nodes` layer in `web/src/cascade/layers.ts`.
- **Why:** The team asked for it: a switched-off substation must read as a failure. It follows the rule in `design.md` that red is for faults.
- **Agents:** The legend card does not list the red dot yet (it only lists line samples). Checked in the browser on the 25F cut: the substations of the island that blacks out turn red at 10,1 s.
- **Files:** `web/src/cascade/layers.ts`.

## 2026-11-21 · feat(web): rebuild mapa 3 on the Design v5 interface

- **Changed:** Mapa 3 (`/`) follows the three Paper "Design v5" frames: 200 px nav rail with the sub50 wordmark and scenarios (Apagón 25F, the active cut, Escenario nuevo), a 440 px docked panel with the Red and Simulación tabs, a timeline card with numbered event markers and island frequency curves, a time pill that picks the operating point, square map controls with a layers popover (2D or 3D, flow, demand), and a legend that switches between voltage and load. Event pins and a callout sit on the map. Styles live in the new `web/src/cascade/cascade.css`; the old mapa 3 block left `styles.css`, which now also holds the Roboto tokens and square corners for the legacy classes.
- **Why:** Ignacio asked for the Design v5 UI with all the functionality of the current cascade viewer, on the Mapbox basemap.
- **Agents:** Playback is now continuous in seconds (`web/src/cascade/simulation.ts`): dark substations wait for their `island_blackout` event, people and lost load between events are an interpolation that ends exactly at the engine summary (`docs/mapa3.md` section 5.1). 2D is the default; `?vista=3d` tilts. The URL is rewritten with `point`, `cut` and `vista`. `MAX_BOUNDS` widened to lon -110 to -35 so the whole country fits at 1440 px; the panel is the Mapbox camera padding. Mapbox uses the Standard style with `theme: "monochrome"`. Islands are "Isla 1", "Isla 2" because the cache has no island zone. "Qué lo habría evitado" and "Validación" are disabled. Mapbox needs `VITE_MAPBOX_TOKEN` in `web/.env.local`; the repo-root `.env` is not read by Vite.
- **Files:** `web/src/cascade/*` (new: `simulation.ts`, `Timeline.tsx`, `SimulationPanel.tsx`, `MapLegend.tsx`, `MapOverlays.tsx`, `ui.tsx`, `cascade.css`, `simulation.test.ts`), `web/src/map/baseMap.ts`, `web/src/map/gridData.test.ts`, `web/src/styles.css`, `docs/mapa3.md`, `docs/design.md`, `web/README.md`.

## 2026-11-21 · feat(web): use the Roboto superfamily and square corners

- **Changed:** `web/package.json` adds `@fontsource-variable/roboto`, `roboto-condensed` and `roboto-mono`; `web/src/main.tsx` imports them. `docs/design.md` section 2: the type rule is now the Roboto superfamily (replacing the Geist pair) and the corner rule is radius 0 on every container, card, button, tag, input and the time pill in the whole app; the layout bullet says "square-cornered floating panel".
- **Why:** Ignacio chose Roboto as the main face with faces from the same family as secondaries, and the team extended Valentina's square-corner rule from the Battle Page to the whole app.
- **Agents:** Faces come from npm, so the app needs no internet for fonts. Use the tokens `--font-sans`, `--font-condensed` and `--font-mono` (defined in `web/src/styles.css` in the next commit), never a font name. Display numbers never use Mono. The Paper `--radius-*` tokens are unchanged for older pages; do not use them on new work.
- **Files:** `web/package.json`, `web/package-lock.json`, `web/src/main.tsx`, `docs/design.md`.

## 2026-11-21 · docs(design): add the Design v5 page and its polish rules

- **Changed:** `docs/design.md` section 1 lists the Paper page "Design v5" (copies of the three v4 frames with the council's fixes applied) as the current reference for the map and the simulation, and marks Design v4 as superseded. New section 3.2 records the v5 rules: grid and panel edges, type scale, small-text contrast, the `--color-fault` token, one event marker style, timeline geometry with a shared frequency scale, legend behaviour, map callouts and wording.
- **Why:** A three-round council review of Design v4 (Claude Opus 5.5, GPT 6.2 Sol, Gemini 4 Neon, Claude Fable 5.2) found layout bugs (V2 nav and panel off-grid, a double-stacked timeline track), contrast failures (12px faint text on cards, white digits on red at 3.09:1) and inconsistencies between frames. All four reviewers were satisfied with v5 (final scores 9.0, 9.2, 9.0, 8.7 out of 10).
- **Agents:** Build the map and simulation UI from Design v5, not v4. The Paper file has a new token `--color-fault` #FF5A48; digits on filled red use #18191B. The V1 km headline now equals the sum of the voltage rows (34.555); the mockup numbers remain invented (section 5). Still open: 500 kV near-white vs magenta, gray vs cream city labels, and whether Valentina's 0 to 2px corners and docked panels (section 2) extend to the whole app, which would require another pass on v5's rounded floating panel.
- **Files:** `docs/design.md`, `CHANGELOG.md`.

## 2026-11-21 · docs(design): record Valentina's Battle Page review

- **Changed:** `docs/design.md` section 2 gets six rules from Valentina's review: Geist Sans only with tabular figures, 0 to 2px corners, panels docked to the nav rail and artboard edges, the event panel as an incident sheet, red and blue as the only battle colors, and effect-based wording.
- **Why:** Valentina reviewed the Battle Page design; the rules are already applied to the Battle Page artboards each bullet names.
- **Agents:** The corner and docking rules cover the Battle Page only. Whether they extend to the whole app is an open team decision: the "rounded floating panel" layout bullet and the `--radius-*` tokens are unchanged. B11 (floating HUD and log) and B7 (green and yellow move notation) are not updated yet.
- **Files:** `docs/design.md`, `CHANGELOG.md`.

## 2026-11-21 · docs(health): document the health index and flag stale 25F figures

- **Changed:** New `docs/health.md` (rule, metrics with limits and sources, 25F against `feb2025-0300`, cautions). `architecture.md` lists the command and `health.yaml`. `engine.md`, `mapa3.md` and `minimum-dataset.md` carry a note that cutting R239 at `feb2025-1500` now gives 1,972 MW lost and 3.8 M people with `voltage_limited`, not 7,872 MW and 15.2 M.
- **Why:** The code is the current state (`AGENTS.md` 1.4); the older figures no longer hold.
- **Agents:** The cause of the change in the R239 result was not investigated, and the "cuts with no effect" column of `engine.md` was not re-run. The `minimum-dataset.md` section 2.4 worked case is out of date.
- **Files:** `docs/health.md`, `docs/architecture.md`, `docs/engine.md`, `docs/mapa3.md`, `docs/minimum-dataset.md`.

## 2026-11-21 · feat(cascade): add the cascadasen-health command

- **Changed:** New `application/grid_health.py` and script `cascadasen-health`: prints the health index of operating points before a fault and after a cut (default `feb2025-1500` and `feb2025-0300`, cut `R239`), or JSON with `--json`. New validation test: the 25F scores below the reference both before and after the cut, limited by `transfer_25f` before it.
- **Why:** Compare the 25F with a healthy point. Result: pre-fault 0.00 against 0.35; after R239, 0.00 (uncertain, `voltage_limited`) against 0.67.
- **Agents:** `uv run cascadasen-health --points <ids> --cut <lines>`; no `--cut` gives pre-fault only. The validation test skips without `data/processed`.
- **Files:** `backend/src/cascadasen/application/grid_health.py`, `backend/pyproject.toml`, `backend/tests/validation/test_health_25f.py`.

## 2026-11-21 · feat(cascade): add the grid health index by margin to the limit

- **Changed:** New `domain/cascade/health.py` (pure) with `params/health.yaml`: margins 0-1 (1 with room, 0 at the limit, `raw` below 0 beyond it) and an index equal to their minimum. Pre-fault: 25F corridor transfer, inertia, frequency after losing the largest synchronous bus, share of single cuts with no effect. After a cut: load served and island frequency. `engine._zone_load` is now public `zone_load`.
- **Why:** Ricardo asked for a health metric to compare the 25F with a healthy operating point.
- **Agents:** Our own model index, not an official indicator; limits marked `is_assumption` are placeholders. `n1_worst` is reported but outside the minimum (cutting a reduced line cuts the whole corridor). Run tests with `uv run pytest` (not `--active`).
- **Files:** `backend/src/cascadasen/domain/cascade/health.py`, `backend/src/cascadasen/domain/cascade/params/health.yaml`, `backend/src/cascadasen/domain/cascade/engine.py`, `backend/tests/unit/test_health.py`.

## 2026-11-21 · feat(web): add the Sub50 favicon
- **Changed:** New `web/public/favicon.svg` (763 bytes): the logo's subscript "5" and power-button "0" in black on a white 32 x 32 tile. `web/index.html` links it with `<link rel="icon" type="image/svg+xml">`.
- **Why:** The site had no favicon; the full "sub50" wordmark from the Paper "Logo" page is unreadable at tab size.
- **Agents:** The "5" is Geist Variable at `wght` 800 (the `geist` npm package) outlined with fontTools, so the SVG needs no font. To regenerate it, outline the glyph again rather than adding a `<text>` element. No PNG or `.ico` fallback exists yet; add one only if a target browser lacks SVG favicon support.
- **Files:** `web/public/favicon.svg`, `web/index.html`, `docs/design.md`.
## 2026-11-21 · feat(web): keep the mapa 3 camera over land
- **Changed:** New `web/src/map/regionLimit.ts` (point in polygon, `nearLand`, viewport radius) with tests. `baseMap.ts` loads the land outlines in `LAND_URLS` (today `chile.geojson`) and, after every `moveend`, snaps the camera back to the last valid center when the center is farther from land than a quarter of the shorter viewport side.
- **Why:** The sea (and Argentina's interior) could be zoomed into. A `maxBounds` rectangle cannot follow Chile's long, thin shape: a tight one forces a high minimum zoom on wide screens and hides the country.
- **Agents:** To add countries, put their land GeoJSON URL in `LAND_URLS` and widen `MAX_BOUNDS`. Only the Mapbox map snaps back; the offline deck.gl fallback keeps the zoom limits only. `?limite=0` disables it. Checked in headless Chrome: Pacific at zoom 9 returns to Santiago, Santiago at zoom 10 stays.
- **Files:** `web/src/map/baseMap.ts`, `web/src/map/regionLimit.ts`, `web/src/map/regionLimit.test.ts`, `web/README.md`.
## 2026-11-21 · docs(architecture): document the system as built

- **Changed:** New `docs/architecture.md`: system overview (sources → `data/processed` → API and static cache → web), backend ports and adapters with the dependency rule, the five ports and their adapters, domain modules (two engines, theatre, agents), use cases and CLI commands, the cut and theatre-cycle flows, frontend, data and parameters, deployment and tooling. `stack.md` sections 2-3 point to it and drop the stale `network.json`/`engine/` backlog entries; `AGENTS.md` and `backend/README.md` link it.
- **Why:** Ricardo asked for architecture documentation; only the README's data-layer diagram existed and `stack.md` described the original target.
- **Agents:** Keep `docs/architecture.md` in sync when a layer, port, engine, CLI command or deployment piece changes. `domain/` must not import from `api/`, `application/` or `infrastructure/`.
- **Files:** `docs/architecture.md`, `docs/stack.md`, `AGENTS.md`, `backend/README.md`.

## 2026-11-21 · fix(web): rename the site title from CascadaSEN to Sub50
- **Changed:** The browser tab `<title>` in `web/index.html` and the panel `<h1>` in `web/src/App.tsx` now read "Sub50".
- **Why:** The project is called Sub50; the site still showed the old name.
- **Agents:** The backend package is still `cascadasen` (`backend/src/cascadasen/`); it was not renamed because users never see it and renaming it touches every import.
- **Files:** `web/index.html`, `web/src/App.tsx`.
## 2026-11-21 · fix(backend): make ruff check and format pass in CI
- **Changed:** `zip(..., strict=True)` for flows and lines in `engine.py` (B905), unquoted type annotation in `scenario.py` (UP037), sorted imports in `test_cascade.py` (I001), and `ruff format` on 7 cascade files (`cache_builder.py`, `engine.py`, `flow.py`, `frequency.py`, `network.py`, `scenario.py`, `test_cascade.py`). No behaviour change; 41 tests pass.
- **Why:** The lint workflow failed on 4 ruff errors and the format check on 7 files.
- **Agents:** CI runs `ruff check .` and `ruff format --check .` (ruff 0.17.6). Run `scripts/lint.sh --fix <files>` on every Python file you touch. The cache in `web/public/cache/` needs no regeneration.
- **Files:** `backend/src/cascadasen/application/cache_builder.py`, `backend/src/cascadasen/domain/cascade/*.py`, `backend/tests/unit/test_cascade.py`.
## 2026-11-21 · perf(web): limit the mapa 3 camera to Chile and lighten the Mapbox style
- **Changed:** `baseMap.ts` sets `maxBounds` (lon -85 to -55, lat -60 to -10), `minZoom` 4 and `maxZoom` 13 on the Mapbox map and the same zoom limits on the offline deck.gl map. The Standard style config turns off `show3dObjects`, `showPointOfInterestLabels`, `showTransitLabels` and `showPedestrianRoads`.
- **Why:** The whole world was reachable although the data covers only Chile; the team wants to cut rendering cost. Effect not measured yet.
- **Agents:** `?limite=0` disables all of it for A/B comparison. The offline map only gets the zoom limits, not a pan limit. 3D buildings are gone from the 3D view; revert `LITE_BASEMAP` if the team wants them back. Mapbox billing (per map load) does not change.
- **Files:** `web/src/map/baseMap.ts`, `web/README.md`.

## 2026-11-21 · docs(agents): operation view pending outside this backend PR

- **Changed:** `docs/agents.md` pending item 2 no longer points to `web/src/operation/`, which this branch removed; drawing the physical readings waits for the frontend PR.
- **Why:** The physical-bots commits were moved onto `feat/strategic-sim-api`, which is backend only.
- **Agents:** The snapshot fields (`observed.areas[].freq_hz`, `rocof_hz_s`, `transient.islands[]`) are the contract the frontend PR should read.
- **Files:** `docs/agents.md`.

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

## 2026-11-21 · revert(web): remove the operation tab; this PR is backend only

- **Changed:** `web/` is back to the state merged from main (`5c62e7b`): removed `web/src/operation/`, the Corte/Operación tabs and `FrequencyChart.tsx` extraction in `CascadeApp.tsx`, the operation styles, the Vite `/api` proxy and the README section. `docker-compose.yml` drops the web→backend wiring (`VITE_API_TARGET`, `depends_on`); the backend LLM options (env file, AWS variables, `WITH_LLM`) stay. `docs/mapa3.md` section 10 is again the backend contract (now listing `llm` in snapshots, `GET /sim/runs/{id}/snapshots` and `catalog.llm`); `docs/docker.md` says the web does not call the backend yet.
- **Why:** Ricardo: the scope of this PR is the backend; the visual layer is separate frontend work.
- **Agents:** Earlier entries describing the operation tab (`feat(web): ...`, `chore(web): proxy ...`, `docs(web): ...`) are superseded by this one; the code is in git history (`fbf8ef9`, `5b19c2f`) if the frontend work wants to reuse it. Backend endpoints and the `llm` snapshot field remain.
- **Files:** `web/**`, `docker-compose.yml`, `docs/mapa3.md`, `docs/docker.md`.

## 2026-11-21 · fix(web): Spanish ISR cause in the operation panel

- **Changed:** The ISR line shows "sin anomalía", "falla" or "intencional" instead of the raw `none` / `failure` / `intentional`.
- **Why:** Seen in the visual check with Qwen as commander (14 cycles: Qwen decided in 12, explanations in Spanish, cascades and crews visible, no console errors).
- **Agents:** UI strings stay in Spanish (AGENTS.md section 4).
- **Files:** `web/src/operation/OperationPanel.tsx`.

## 2026-11-21 · feat(web): show the AI commander and a live overlay in the operation tab

- **Changed:** Backend: each snapshot carries `llm` (status `chosen` / `unavailable` / `idle` / `replayed`, model, chosen keys, explanation, options, capacity); `GET /sim/catalog` adds `llm: {available, model}`. Frontend: "Comandante con IA" checkbox (live API with an LLM configured), "pensando…" state while the model decides, AI card with the picked options and the Spanish explanation, "IA" badges on AI-picked actions, a map overlay (clock, service, level, this cycle's events coloured by source, AI explanation), pulsing rings on the areas where actions run (magenta = AI, cyan = rules), larger area circles and crew labels, Spanish accents in map labels (`characterSet: "auto"`).
- **Why:** Ricardo wants to see clearly, and visually, what the models and agents do in each cycle.
- **Agents:** Visually checked with headless Chromium (Playwright from the npx cache) against the real API: 12 cycles, cascades on cycles 6 and 10, no console errors. The LLM itself was not reachable from that environment (no AWS credentials), so the AI card showed "no disponible"; the Qwen path is covered by `test_llm_commander.py` and Ricardo's manual call.
- **Files:** `backend/src/cascadasen/domain/theater/cycle.py`, `backend/src/cascadasen/application/simulation_service.py`, `backend/tests/unit/test_llm_commander.py`, `web/src/operation/{types,layers}.ts`, `web/src/operation/OperationPanel.tsx`, `web/src/styles.css`.

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
## 2026-11-21 · feat(infra): CLI-only deploy workflow with CloudFront invalidation
- **Changed:** `.github/workflows/deploy.yml` no longer runs Terraform: it builds and pushes both images, registers a new task definition revision, updates the ECS service, waits for stable, and invalidates CloudFront. The role ARN is hardcoded (`IAM-Role-ECS-Deploy`). New `infrastructure/deploy-role-policy.json` (minimal permissions for that role). `aws_ecs_service.app` gets `ignore_changes = [task_definition]`.
- **Why:** The deploy only needs a new image tag; Terraform needed broad IAM permissions and a state bucket. Repository variables cannot be edited, so the ARN cannot come from `AWS_DEPLOY_ROLE_ARN`.
- **Agents:** The previous entry's `AWS_DEPLOY_ROLE_ARN` requirement is obsolete. The workflow does not apply infrastructure changes: run `infrastructure/deploy.sh` by hand for those. Apply the `ecs.tf` lifecycle change once with `deploy.sh`. The role trust `sub` uses owner and repository IDs; fall back to the classic `sub` if the role cannot be assumed. Pushing the workflow file needs the `workflow` token scope.
- **Files:** `.github/workflows/deploy.yml`, `infrastructure/deploy-role-policy.json`, `infrastructure/ecs.tf`, `docs/infrastructure.md`.
## 2026-11-21 · fix(web): commit the mapa 3 cache so the deployed site loads
- **Changed:** `web/public/cache/` (23 MB, 1103 files, 4 points x 273 cuts) is now versioned; removed it from `web/.gitignore`. nginx answers a missing `/cache/*` file with 404 instead of the SPA `index.html`. `cascade/api.ts` shows "Falta la caché (...)" when the response is not JSON.
- **Why:** sub50.cl showed `Unexpected token '<', "<!doctype "...`: the cache was git-ignored, so the web image had none and nginx returned `index.html` with 200.
- **Agents:** Regenerate (`cd backend && uv run cascadasen-cache`) and commit the cache whenever the engine or `data/processed` change, or the deployed site serves stale results. Older docs that say the cache is git-ignored are fixed in `web/README.md` and `docs/mapa3.md`.
- **Files:** `web/public/cache/`, `web/.gitignore`, `infrastructure/docker/nginx.conf`, `web/src/cascade/api.ts`, `web/README.md`, `docs/mapa3.md`.
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

## 2026-11-21 · docs(design): add Design v4 page and simulation color rules

- **Changed:** `docs/design.md` section 1 lists the new Paper page "Design v4" (V1 Red, V2 Simulación en curso, V3 Después del corte) as the current reference for the map and the simulation; Design v3 stays the reference for zoom levels. New section 3.1 records the v4 rules.
- **Why:** Felipe's review of Design v3: the load legend reused the voltage hues, the event history was disconnected from the map and the timeline, and "Supuestos" took a nav rail slot.
- **Agents:** In the Simulación tab, line color is load on a gray-to-red ramp and stroke width is voltage; never reuse voltage hues for load. Events are numbered once and shown in the panel history, on the timeline and as map pins. Assumptions sit next to their numbers and in a panel row, not in the nav rail. Section 3 still says 500 kV is magenta while v3 and v4 draw it near-white; that row is not fixed yet.
- **Files:** `docs/design.md`, `CHANGELOG.md`.

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
