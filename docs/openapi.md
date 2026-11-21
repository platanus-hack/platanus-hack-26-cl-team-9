# Agent-only OpenAPI spec

External agents (and the MCP server that wraps them, `docs/mcp.md`) get a separate OpenAPI 3.1 spec that holds only the endpoints they need. The full spec stays at `/docs`, `/redoc` and `/openapi.json`.

| What | Where |
|---|---|
| Live spec | `GET /api/v1/agents/openapi.json` (public at `https://sub50.cl/api/v1/agents/openapi.json` through the ALB rule `/api/*`) |
| Swagger page | `GET /api/v1/agents/docs` |
| Versioned file | `docs/openapi/agents.openapi.json` |
| Code | `backend/src/cascadasen/api/agent_openapi.py` (marker, `ErrorResponse`, `errors()`, spec builder) |
| Drift test | `backend/tests/integration/test_agent_openapi.py` |
| Regenerate | `cd backend && uv run python -m cascadasen.api.agent_openapi` |
| Validate | `uvx openapi-spec-validator docs/openapi/agents.openapi.json` |

## Conventions for agent routes

Every route an external agent calls follows these rules. They are shared with the session API (`/api/v1/sessions/*`) so the spec can become MCP tools without renaming.

1. **Marker.** Mark the route with `openapi_extra=AGENT` (`{"x-sub50-agent": True}`, from `cascadasen.api.agent_openapi`). The agent spec includes exactly the marked routes; nothing is filtered by tag or path.
2. **Scope.** Marked: session create, get and delete; session network read (`GET /sessions/{sid}/network`, the 188-bus network with defaults from the base dataset when the session has no edits); CRUD of buses, lines, loads or datacenters, and generators; reset; sandbox cut, repair and state; session runs and their subresources (create, get, events, step, replay, snapshots, trace, report, after_action, actions); the catalog (`/sim/catalog`). The global `/sim/runs*` and `/sim/network` stay marked until sessions exist. Not marked: grid queries over the full snapshot (`/nodes`, `/edges`, `/graph/*`, `/plants`, ...), `/simulate`, campaigns, narrative, health, admin, and the SSE stream `/sessions/{sid}/events` (not usable as an MCP tool).
3. **operationId.** Set `operation_id=` explicitly: snake_case, `verb_noun`, unique and stable. Names: `create_session`, `get_session`, `delete_session`, `get_session_network`, `add_bus`, `update_bus`, `delete_bus`, `add_line`, `update_line`, `delete_line`, `add_load`, `update_load`, `delete_load`, `add_generator`, `update_generator`, `delete_generator`, `reset_session`, `cut_lines`, `repair_lines`, `get_cut_state`, `create_run`, `get_run`, `inject_run_event`, `step_run`, `replay_run`, `get_run_snapshots`, `get_run_trace`, `get_run_report`, `get_run_after_action`, `submit_run_action`, `get_catalog`. Global routes take the prefix `global_` (`global_create_run`, `global_get_run`, ..., and `global_get_network` for `/sim/network`) so they never collide with the session ones.
4. **Text.** English `summary` (one line) and `description`: what it does, when an agent should call it, side effects, which ids it accepts and where to get them. Path, query and body parameters carry `description` and `examples` (`Path(...)`, `Query(...)` or pydantic `Field(..., description=..., examples=[...])`).
5. **Errors.** Declare every code the route can return among 404, 409, 412, 422 and 429 with `responses=errors({code: "one-line description"})`. All of them use the shared `ErrorResponse {detail}`. Declare 422 on every route with parameters or a body, so FastAPI's default `HTTPValidationError` does not appear. `detail` is a Spanish string, or an object `{field, message, valid}` for simulator input errors, or FastAPI's validation list; the contract wrote `detail: str`, the model widens it to match what the routes really return.
6. **Success body.** Document the 2xx body with a response model in `responses=` (`ok(Model)` or `ok(Model, 201)`, from `agent_openapi.py`), never `response_model=`, so the runtime body does not change (a `response_model` would validate and reorder it; `response_model=None` turns a NaN into a 500). Models derive from `AgentOut` (`extra="allow"`, because outputs carry more keys than documented) and live in `api/simulation_schemas.py` or `api/session_schemas.py`; only always-present keys are required. `agent_openapi()` keeps only the `$ref` in each 2xx JSON schema. The exceptions are `delete_session` (204, no body) and `global_create_run`/`global_replay_run`, which already use `response_model=RunSummary`.
7. **Tags.** `sessions`, `session-network`, `session-sandbox`, `session-runs`, `catalog`, plus `global-runs` for `/sim/runs*` and `/sim/network`. Tag descriptions live in `TAGS` in `agent_openapi.py`; only the tags in use appear in the spec.
8. **Versioned file.** Whoever adds or changes a marked route, or a model those routes use, regenerates `docs/openapi/agents.openapi.json` in the same commit. The test fails when the committed file differs from the app, and also checks the marker set, unique snake_case ids, summary, description, parameter descriptions and examples, that every request-body field has a description, and that every 2xx JSON body is a `$ref` to a model with properties.

Spec metadata (title, version, the description that explains ids, sessions and the simulated-consequence notice) is in `agent_openapi.py`. Bump `VERSION` when an operationId or a request body changes in a way that breaks a client.
