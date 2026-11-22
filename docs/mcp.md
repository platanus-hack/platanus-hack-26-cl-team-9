# MCP server: simulations in natural language

An MCP server wraps the agent API (`docs/sessions-api.md`, `docs/openapi.md`) so a client with an LLM (Claude Code, Claude Desktop, another agent) can run simulations by talking. The LLM lives in the client; Sub50 supplies the tools. It adds to the strategic theatre and its bots (`docs/agents.md`, `docs/cyber.md`); it does not replace or change them.

Code: `backend/src/cascadasen/mcp/`. Tests: `tests/unit/test_mcp_tools.py`, `tests/integration/test_mcp_server.py`.

## 1. Run it

```bash
cd backend && uv run cascadasen-api                       # the API, http://localhost:8000
claude mcp add sub50 --env SUB50_API_URL=http://localhost:8000 -- \
  uv run --directory /abs/path/to/backend --extra mcp cascadasen-mcp
```

| Setting | Default | Meaning |
|---|---|---|
| `SUB50_API_URL` | `http://localhost:8000` | API base URL, for example `https://sub50.cl` |
| `SUB50_AGENT` | `mcp` | Name sent in `X-Sub50-Agent`, recorded in the session's `last_op.by` (64 characters) |

Transport is stdio. The process holds the active session and run in memory only: the session id is a capability (`sessions-api.md` section 1), so it is never written to disk. `httpx` logging is set to WARNING because its INFO lines print URLs with the id. A remote HTTP transport and API authentication are not done (the API has no key). The same tools also run inside the backend behind a chat endpoint, with no MCP client: `docs/assistant.md`.

## 2. Layout

| File | Role |
|---|---|
| `client.py` | `Sub50Client` over `httpx`: sends `X-Sub50-Agent`, retries a 409 once (after `Retry-After`, for any method, when the session is busy with another request; at once for a write another instance won), turns 429 into "wait N seconds" and any error into `ToolError` with the API's Spanish `detail` and `valid` list |
| `state.py` | `McpState`: active session id and run id, so the user never repeats ids |
| `digest.py` | Compact summaries (a whole network is 188 buses; a step has frames and per-area detail) and name resolution (`resolve_bus`) |
| `tools.py` | One method per tool; `OPERATIONS` maps each tool to the agent-API operationIds it calls |
| `server.py` | `MCPServer` (SDK `mcp` 2.x), `INSTRUCTIONS`, entry point `cascadasen-mcp` |

A session serves one request at a time (`sessions-api.md` section 7), so a tool call may wait up to 10 s behind another client's request; the busy 409 is retried once after its `Retry-After` and then shown to the model. Edits send no `If-Match`: each edit applies to the freshly read document and operations do not overwrite each other's elements (`sessions-api.md` section 7). A conditional edit needs the raw API.

## 3. Tools

| Group | Tools |
|---|---|
| Session | `start_session`, `join_session`, `end_session`, `list_options`, `describe_network` |
| Network edits | `add_datacenter`, `add_generator`, `add_line`, `add_bus`, `edit_element`, `remove_element`, `reset_network` |
| Sandbox | `cut_lines` (1-3 lines), `repair_lines`, `get_grid_state` |
| Incidents | `list_incident_scenarios`, `start_incident_run` |
| Strategic runs | `start_run`, `inject_event`, `step`, `submit_action`, `run_status`, `run_report`, `after_action`, `replay` |
| Prepared scenarios (no session) | `prepare_scenario`: batch changes by filters plus failures, then the cascade (`docs/stress.md`) |

- Where `add_datacenter` or `add_generator` take a bus, a `B###` id or the exact name of a bus of the session resolves locally; any other place (a city, comuna, substation name, region or area) goes to `GET /grids/places` (agent operation `resolve_place`, `stress.md` section 3.1), so "Iquique" lands at the substation that serves Iquique. The result carries `placed` (how it was resolved). Until 2026-11-22 area names matched first: "Antofagasta" went to S/E ESCONDIDA and "Arica" to S/E COLLAHUASI. `add_generator` accepts common technology names ("eólica", "nuclear" as `termica` with a `note`); a battery only exists in `prepare_scenario` (`tech: bateria`). The redispatch of an edit carries `meaning` ("las centrales sincrónicas de la isla bajan 200 MW…").
- Edits return the new id, where it went (`bus`, `bus_name`, `area`, `area_name`), `warnings`, the redispatch rule with `is_assumption: true` and the baseline after the edit: `newly_overloaded` (caused by the edit), `still_overloaded` (overloaded before and after), `no_longer_overloaded` (relieved), `overloaded_now_total` and `load_shed_mw`. The base case already has overloaded lines, so only `newly_overloaded` is the edit's doing. `describe_network` keeps `baseline.overloaded_lines` (the current list) and lists the corridors with their lines; with `focus` it gives the area's totals and its overloaded lines.
- `step` returns, per cycle, `unserved_mw` (power, not energy) and `level_text` (the official label, e.g. "L1 · contenido"), plus `events_applied` for the whole call and a `warning` when no event happened, so a summary cannot claim an event that was not applied. `run_report` adds `consequence.worst_level_text`.
- A corridor between areas (`A06-A07`) is a group of lines: `cut_lines` takes only real line ids; a whole corridor opens in a strategic run with `inject_event(C3_transmission_opening, "A06-A07")`. `start_run` keeps `open_field` (no scripted events) unless the user names another template.
- `start_incident_run(scenario, policy, seed)` replays a documented incident (ids from `list_incident_scenarios`: Huatacondo, Poland, UK, 25F) in the active session and makes its run the active one; then use `step`, `run_report` (its `incident` has the consequence card, with the cost method and its sources, and the mitigations) and `after_action` (it adds the incident section). No tool accepts free effects or lists targets (`attack-sim.md` section 3.1).
- Ids for events, actions, policies and templates come from `list_options` (the catalog).
- `prepare_scenario` works on the default grid, not on a session. It takes `changes` (population, demand, generation, lines, by filters: places, buses, zones, areas, comunas, tech, lines, kv; a new point is `places` with `add`), `open_lines`, `out_buses` and `point`. It calls `POST /grids/prepare` and, with failures, `POST /grids/simulate` with and without the changes. Each call is the full final state: in the web it replaces the grid on the map, paused at 0. Guide with fields, recipes and errors: `docs/stress.md`.

## 4. Guardrails

Same as `cyber.md` section 8 and `sessions-api.md` section 11:

- No tool searches, ranks or suggests the worst cut or area, and none loops over lines. `cut_lines` takes 1-3 lines and the API rate limits stay in force (the MCP does not hide a 429). A test fails if a tool name suggests ranking.
- Results carry `notice: "Escenario hipotético: se modela el efecto, no el ataque."` The server `instructions` tell the model to describe effects and prevention only, and to label modelled values as assumptions.
- The adversary stays the seeded abstract one: `start_run(adversary_objective=...)` picks an objective from the catalog; no tool lets the model choose targets for it.

## 5. Adding or changing a tool

1. Add the method to `Sub50Tools` (docstring = the description the model reads) and its entry in `OPERATIONS`.
2. Keep the result small: add a digest to `digest.py` rather than returning raw responses.
3. If an operationId changes in the API, `test_every_tool_maps_to_an_operation_of_the_agent_spec` fails; update `OPERATIONS`.
