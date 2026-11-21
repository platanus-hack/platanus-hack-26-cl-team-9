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

Transport is stdio. The process holds the active session and run in memory only: the session id is a capability (`sessions-api.md` section 1), so it is never written to disk. `httpx` logging is set to WARNING because its INFO lines print URLs with the id. A remote HTTP transport and API authentication are not done (the API has no key).

## 2. Layout

| File | Role |
|---|---|
| `client.py` | `Sub50Client` over `httpx`: sends `X-Sub50-Agent`, retries a 409 once, turns 429 into "wait N seconds" and any error into `ToolError` with the API's Spanish `detail` and `valid` list |
| `state.py` | `McpState`: active session id and run id, so the user never repeats ids |
| `digest.py` | Compact summaries (a whole network is 188 buses; a step has frames and per-area detail) and name resolution (`resolve_bus`) |
| `tools.py` | One method per tool; `OPERATIONS` maps each tool to the agent-API operationIds it calls |
| `server.py` | `MCPServer` (SDK `mcp` 2.x), `INSTRUCTIONS`, entry point `cascadasen-mcp` |

Edits send no `If-Match`: each edit applies to the freshly read document and operations do not overwrite each other's elements (`sessions-api.md` section 7). A conditional edit needs the raw API.

## 3. Tools

| Group | Tools |
|---|---|
| Session | `start_session`, `join_session`, `end_session`, `list_options`, `describe_network` |
| Network edits | `add_datacenter`, `add_generator`, `add_line`, `add_bus`, `edit_element`, `remove_element`, `reset_network` |
| Sandbox | `cut_lines` (1-3 lines), `repair_lines`, `get_grid_state` |
| Strategic runs | `start_run`, `inject_event`, `step`, `submit_action`, `run_status`, `run_report`, `after_action`, `replay` |

- Where a tool takes a bus it accepts `B###`, an area id or name (`A02`, "Antofagasta", which maps to the area's anchor bus) or a unique part of a bus name; otherwise it answers with the candidate ids.
- Edits return the new id, `warnings`, the redispatch rule with `is_assumption: true` and the baseline (`overloaded_lines`, `load_shed_mw`), because a large datacenter can overload lines before any cut.
- Ids for events, actions, policies and templates come from `list_options` (the catalog).

## 4. Guardrails

Same as `cyber.md` section 8 and `sessions-api.md` section 11:

- No tool searches, ranks or suggests the worst cut or area, and none loops over lines. `cut_lines` takes 1-3 lines and the API rate limits stay in force (the MCP does not hide a 429). A test fails if a tool name suggests ranking.
- Results carry `notice: "Escenario hipotético: se modela el efecto, no el ataque."` The server `instructions` tell the model to describe effects and prevention only, and to label modelled values as assumptions.
- The adversary stays the seeded abstract one: `start_run(adversary_objective=...)` picks an objective from the catalog; no tool lets the model choose targets for it.

## 5. Adding or changing a tool

1. Add the method to `Sub50Tools` (docstring = the description the model reads) and its entry in `OPERATIONS`.
2. Keep the result small: add a digest to `digest.py` rather than returning raw responses.
3. If an operationId changes in the API, `test_every_tool_maps_to_an_operation_of_the_agent_spec` fails; update `OPERATIONS`.
