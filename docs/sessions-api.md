# Sessions API: guide for agents and other clients

This guide is for an external agent, script or second browser that works on a shared session. The live schema is at `/docs` (FastAPI); the agent-only spec is at `/api/v1/agents/openapi.json` (versioned in `docs/openapi/agents.openapi.json`). Every route here, except the SSE stream, carries `x-sub50-agent: true` in the OpenAPI spec and follows `docs/openapi.md`. Code: `backend/src/cascadasen/api/session_routes.py`. Data contract of the session document: `docs/stack.md` section 6.2.

## 1. What a session is

A session is an editable copy of the 188-bus engine network (`docs/engine.md`, the mapa 3 network). It holds:

- one **operating point**, pinned when the session is created and never changed. The four points are `feb2025-1500` (25F reference), `feb2025-0300` (minimum demand), `nov2026-1300` (solar midday, the default) and `nov2026-2000` (evening peak). `GET /api/v1/sim/catalog` lists them under `operating_points`;
- an **overlay**: the buses, lines, loads, datacenters and generators the session added, and the overrides of base elements. The base dataset never changes;
- a **sandbox cut**: the lines currently open (`open_lines`), shared by every client of the session;
- the **runs** of the strategic theatre created in the session. Each run keeps the dataset it was created with.

The session is one JSON document in the document store (`sessions/<sid>.json`: memory, file or S3, `CASCADASEN_SESSION_STORE`). Several backend instances can serve the same session. Every change bumps an integer `revision`.

There is no API key. The session id is a capability: whoever has it can read and edit the session. Do not publish it.

## 2. Create and join

```bash
API=http://localhost:8000/api/v1
SID=$(curl -s -X POST "$API/sessions" -H 'Content-Type: application/json' \
  -H 'X-Sub50-Agent: bot-1' -d '{"label": "Equipo 9"}' | jq -r .session_id)
curl -s "$API/sessions/$SID" | jq '{revision, point, share_path, expires_at}'
```

The body is optional; `{"point": "feb2025-1500"}` pins another point. The response carries `share_path: "/?sesion=<sid>"`. The web app does not open a session from `?sesion=<sid>` since #101 (`docs/mapa3.md` section 11); it only joins the session an **Incidentes** run creates. An API client or an MCP client uses the `sid` directly. The server sets no cookie. To join from another machine, use the same `sid`.

## 3. The session id goes in the path

Every agent endpoint of a session takes `{sid}` in the path: `/api/v1/sessions/{sid}/...`. That includes runs: a session run lives at `/api/v1/sessions/{sid}/runs/{rid}`. The grid query endpoints (`/nodes`, `/edges`, `/plants`, `/graph/*`, ...) read the full snapshot, are global and take no `sid`. The global runs `/api/v1/sim/runs*` still exist and run on the base dataset; use the session routes for anything shared.

Ids:

- `sid`: 22 URL-safe characters. Any other shape gives 404.
- `rid`: 12 hex characters, from `POST /sessions/{sid}/runs`. `GET /sessions/{sid}` lists the session's runs under `runs`.
- Buses `B###` (base `B000`-`B187`; added buses continue at `B188`), base lines `R###`, added lines `U###`, loads and datacenters `D###`, generators `G###`. `GET /sessions/{sid}/network` returns them all.

## 4. Endpoints

All paths are under `/api/v1/sessions`. Mutations accept `If-Match: "<revision>"` (section 7) and `X-Sub50-Agent: <name>` (up to 64 characters, recorded in `last_op.by`; default `anon`).

| Method and path | operationId | Body | Response | Codes |
|---|---|---|---|---|
| `POST ""` | `create_session` | `{point?, label?}` | session document | 201, 422, 429 |
| `GET /{sid}` | `get_session` | | session document (`ETag`; `If-None-Match` gives 304) | 200, 304, 404, 409 |
| `DELETE /{sid}` | `delete_session` | | empty | 204, 404, 409, 429 |
| `POST /{sid}/reset` | `reset_session` | optional `{scenario: {point?, changes, open_lines, out_buses}}`: the grid becomes that configuration (changes as overrides, `out_buses` out of service, `open_lines` cut, what the session added is dropped); another `point` gives 422 | `{revision, warnings, balance}` | 200, 404, 409, 412, 429 |
| `GET /{sid}/network` | `get_session_network` | | network view (section 9) | 200, 404, 409 |
| `POST /{sid}/buses` | `add_bus` | `{name, lat, lon, kv}` | `{id, revision, warnings, balance}` | 201, 404, 409, 412, 422, 429 |
| `POST /{sid}/substations` | `add_substation` | `{name, lat, lon, kv, connections: [{to, capacity_mw?, x_pu?}] (1-6), load?: {mw, kind}, generator?: {mw, tech, ...}}`. Every `to` is an existing bus of the same `kv`. All or nothing, one revision | `{id, line_ids, load_id, generator_id, coherence, revision, warnings, balance}`; `coherence` lists plausibility notes (capacity far from the neighbours, line over 300 km, MW above the lines) | 201, 404, 409, 412, 422, 429 |
| `PATCH /{sid}/buses/{element_id}` | `update_bus` | any of `name, kv, lat, lon, load_mw, gen_mw, sync_mw, inertia_mws, in_service` | same | 200, 404, 409, 412, 422, 429 |
| `DELETE /{sid}/buses/{element_id}` | `delete_bus` | | same | 200, 404, 409, 412, 429 |
| `POST /{sid}/lines` | `add_line` | `{a, b, kv, capacity_mw, x_pu?, name?}` | same | 201, ... |
| `PATCH /{sid}/lines/{element_id}` | `update_line` | any of `capacity_mw, x_pu, in_service` | same | 200, ... |
| `DELETE /{sid}/lines/{element_id}` | `delete_line` | | same | 200, ... |
| `POST /{sid}/loads` | `add_load` | `{bus, mw, kind: datacenter\|consumo, name}` | same | 201, ... |
| `PATCH /{sid}/loads/{element_id}` | `update_load` | any of `mw, kind, name, in_service` | same | 200, ... |
| `DELETE /{sid}/loads/{element_id}` | `delete_load` | | same | 200, ... |
| `POST /{sid}/generators` | `add_generator` | `{bus, mw, tech, synchronous?, inertia_h?, name?}` | same | 201, ... |
| `PATCH /{sid}/generators/{element_id}` | `update_generator` | any of `mw, tech, synchronous, inertia_h, name, in_service` | same | 200, ... |
| `DELETE /{sid}/generators/{element_id}` | `delete_generator` | | same | 200, ... |
| `POST /{sid}/cut` | `cut_lines` | `{lines: [1-3 ids]}` | `{revision, open_lines, timeline, notice}` | 200, 404, 409, 412, 422, 429 |
| `POST /{sid}/repair` | `repair_lines` | `{lines: [...]}` or `{all: true}` | same | 200, 404, 409, 412, 422, 429 |
| `GET /{sid}/state` | `get_cut_state` | | same | 200, 404, 409 |
| `GET /{sid}/events` | (not an agent tool) | | `text/event-stream` (section 6) | 200, 404, 429 |
| `POST /{sid}/runs` | `create_run` | the `POST /sim/runs` body (`template, policy, seed, horizon, adversary, capabilities, initial_events, auto_run, stochastic, llm_commander`) | run summary + `session_revision` | 201, 404, 409, 422, 429 |
| `POST /{sid}/attacks/runs` | `start_incident_run` | `{scenario, policy?, seed?, uncertainty?, stochastic?, adversary?}` (`scenario` from `GET /api/v1/attacks/catalog`; `attack-sim.md` section 3.1). The session's `point` must equal the incident's `operating_point`, else 422 with that point in `valid` | run summary + `session_revision` | 201, 404, 409, 422, 429 |
| `GET /{sid}/runs/{rid}` | `get_run` | | `{run, latest, resources, series}` | 200, 404, 409 |
| `POST /{sid}/runs/{rid}/events` | `inject_run_event` | `{type, target, params?, cause?}` | resolved target, `run`, `session_revision` | 200, 404, 409, 422, 429 |
| `POST /{sid}/runs/{rid}/step` | `step_run` | `{cycles: 1-72}` | `{run, snapshots, session_revision}` | 200, 404, 409, 422, 429 |
| `POST /{sid}/runs/{rid}/actions` | `submit_run_action` | `{action, target, role, params?, agent?}` | `{accepted, applies_at_cycle, action, target, role, notice, run, session_revision}` | 200, 404, 409, 422, 429 |
| `POST /{sid}/runs/{rid}/replay` | `replay_run` | `{policy?, uncertainty?, seed?, adversary?, capabilities?, cycles?}` | new run summary + `replay_of` | 201, 404, 409, 422, 429 |
| `GET /{sid}/runs/{rid}/snapshots?start=` | `get_run_snapshots` | | `{run, snapshots}` | 200, 404, 409, 422 |
| `GET /{sid}/runs/{rid}/trace` | `get_run_trace` | | audit log, `head`, `verified`, `recipe` | 200, 404, 409 |
| `GET /{sid}/runs/{rid}/report` | `get_run_report` | | indicators, indices, consequence | 200, 404, 409 |
| `GET /{sid}/runs/{rid}/after_action` | `get_run_after_action` | | after-action report in Spanish | 200, 404, 409 |

Every route can also answer 413 (body over 64 KB) and 422 (malformed headers or body). Every route with `{sid}` except `/events` answers 409 when the session stays busy with another request (section 7). There is no `GET /{sid}/runs` list: the session document holds `runs`.

## 5. Examples

```bash
# a 120 MW datacenter on an existing bus
curl -s -X POST "$API/sessions/$SID/loads" -H 'Content-Type: application/json' -H 'X-Sub50-Agent: bot-1' \
  -d '{"bus": "B010", "mw": 120, "kind": "datacenter", "name": "Datacenter Antofagasta"}'

# a new bus, a line that connects it, and a datacenter on it
curl -s -X POST "$API/sessions/$SID/buses" -H 'Content-Type: application/json' \
  -d '{"name": "SE Datacenter Norte", "lat": -23.70, "lon": -70.35, "kv": 110}'          # -> {"id": "B188", ...}
curl -s -X POST "$API/sessions/$SID/lines" -H 'Content-Type: application/json' \
  -d '{"a": "B010", "b": "B188", "kv": 110, "capacity_mw": 300}'                         # -> {"id": "U001", ...}
curl -s -X POST "$API/sessions/$SID/loads" -H 'Content-Type: application/json' \
  -d '{"bus": "B188", "mw": 80, "kind": "datacenter", "name": "DC Norte"}'

# change and delete a line
curl -s -X PATCH "$API/sessions/$SID/lines/U001" -H 'Content-Type: application/json' -H 'If-Match: "4"' \
  -d '{"capacity_mw": 450}'
curl -s -X PATCH "$API/sessions/$SID/lines/R012" -H 'Content-Type: application/json' -d '{"in_service": false}'
curl -s -X DELETE "$API/sessions/$SID/loads/D002"
curl -s -X DELETE "$API/sessions/$SID/lines/U001"

# a generator
curl -s -X POST "$API/sessions/$SID/generators" -H 'Content-Type: application/json' \
  -d '{"bus": "B010", "mw": 150, "tech": "solar", "name": "Parque solar nuevo"}'

# sandbox: open a line, then close everything
curl -s -X POST "$API/sessions/$SID/cut" -H 'Content-Type: application/json' -d '{"lines": ["R014"]}' \
  | jq '{revision, open_lines, shed: .timeline.summary.load_shed_mw}'
curl -s -X POST "$API/sessions/$SID/repair" -H 'Content-Type: application/json' -d '{"all": true}'

# a run on the session network: create, inject, step, act, replay, trace
RID=$(curl -s -X POST "$API/sessions/$SID/runs" -H 'Content-Type: application/json' \
  -d '{"template": "open_field", "policy": "C", "seed": 7, "horizon": 12}' | jq -r .run_id)
curl -s -X POST "$API/sessions/$SID/runs/$RID/events" -H 'Content-Type: application/json' \
  -d '{"type": "C3_transmission_opening", "target": "A06-A07"}'
curl -s -X POST "$API/sessions/$SID/runs/$RID/step" -H 'Content-Type: application/json' -d '{"cycles": 1}'
curl -s -X POST "$API/sessions/$SID/runs/$RID/actions" -H 'Content-Type: application/json' -H 'X-Sub50-Agent: bot-1' \
  -d '{"action": "restore_element", "target": "A06-A07", "role": "operations", "agent": "bot-1"}'
curl -s -X POST "$API/sessions/$SID/runs/$RID/step" -H 'Content-Type: application/json' -d '{"cycles": 1}' \
  | jq '.snapshots[0].executed'
curl -s -X POST "$API/sessions/$SID/runs/$RID/replay" -H 'Content-Type: application/json' -d '{"policy": "A"}'
curl -s "$API/sessions/$SID/runs/$RID/trace" | jq '{verified, head}'
```

Run actions: `action` comes from `GET /api/v1/sim/catalog` (`actions`), `role` must be one of that action's proposers (for `restore_element`: `operations`), and `target` an area (`A01`-`A13`) or corridor (`A06-A07`). The action is checked for structure at once (unknown action or role gives 422, unknown target 404) and runs in the next cycle. When it executes it goes through the same validator, resource and crew checks as the commander's own actions and spends one unit of operator attention. It is not capped by C2's operator attention capacity (4 per cycle) and it skips C2's choice, the conflict rules between actions and the stabilisation and logistics vetoes: it executes even when C2 rejected the same action, and several external actions in one cycle all execute. Rate limits (section 8) are the only bound on how many an agent submits. A finished run gives 409.

## 6. Live updates (SSE)

`GET /api/v1/sessions/{sid}/events` is a `text/event-stream`:

```
retry: 2000
id: 3
event: revision
data: {"type": "revision", "revision": 3, "dataset_revision": 2, "op": "load_added", "ids": ["D001"], "by": "bot-1"}

: ping
```

- The first event comes on connect and carries the current revision. Another `revision` event follows every change (`op` is one of `created`, `bus_added`, `line_updated`, `load_removed`, ..., `reset`, `cut`, `repair`, `run_created`, `run_updated`).
- `: ping` comments arrive every 15 s (`CASCADASEN_SSE_HEARTBEAT_S`). The server polls its cached copy every second and the store every 5 s, so a change made on another instance shows within about 5 s; on the same instance within about 1 s.
- The server closes the stream after 55 s (`CASCADASEN_SSE_MAX_S`). `EventSource` reconnects by itself after `retry` (2 s) and sends `Last-Event-ID`; the server ignores it and starts again with the current revision, which is all a client needs.
- The stream ends when the session is deleted or expires.
- At most 5 open streams per session and client IP (`CASCADASEN_SSE_PER_SESSION_IP`), else 429.
- The stream does not take the session lock (section 7): it is long-lived, so it neither waits for other requests nor makes them wait.
- Rule for clients: when `dataset_revision` moved, refetch what you show (`GET /{sid}/network`, `GET /{sid}/state`). When only `revision` moved (`run_created`, `run_updated`), the dataset is the same: refetch `GET /{sid}` if you show its `runs`. If you cannot tell, refetch everything, including `GET /{sid}`.
- Polling fallback (no `EventSource`, or a proxy that buffers): `GET /{sid}` every 2 s with `If-None-Match: "<last ETag>"`; 304 means nothing changed.

The SSE route is not an agent tool (it is unmarked in the OpenAPI spec). An agent that cannot hold a stream polls `GET /{sid}` with `If-None-Match`.

## 7. Revisions, ETag, If-Match and one request at a time

- A session document has two counters. `revision` moves on every change, run activity included. `dataset_revision` moves only on what changes the dataset or the sandbox: element edits, reset, cut and repair.
- `GET /{sid}` carries `ETag: "<revision>"` (for `If-None-Match` polling). `/network`, `/state`, every edit, reset, cut and repair carry `ETag: "<dataset_revision>"`. Run commands that change the session return `session_revision` (the `revision`) and the same header.
- Send `If-Match: "<dataset_revision>"` on an edit, reset, cut or repair to make it conditional: if someone else changed the dataset first, the request is refused with 412 and nothing changes. A run stepped by another agent does not cause a 412. Re-read, decide again, retry. Without `If-Match` the edit applies to whatever the current revision is (last writer wins per operation; operations never overwrite each other's elements, because each edit is applied to the freshly read document).
- Between instances, writes are conditional on the store's etag and retried 3 times; after that the API answers 409 and the client retries.
- One request at a time per session. In a backend process, every request with `{sid}` in the path (reads, edits, reset, cut, repair, delete and every run route) holds a lock on that session, so requests on one session run one after another; different sessions run in parallel. `GET /{sid}/events` (SSE) and `POST ""` do not take it. A request waits up to 10 s (`CASCADASEN_SESSION_LOCK_TIMEOUT_S`) for the one before it, then gets 409 `"La sesión está ocupada con otra solicitud; reintenta."` with `Retry-After: 1`; retry it. At most 10 requests wait behind the one in progress (`CASCADASEN_SESSION_LOCK_MAX_WAITERS`); a further one gets the same 409 at once, so one session cannot hold every worker of the process. Trade-off: each waiter blocks one of AnyIO's 40 default sync workers for up to 10 s, so one busy session holds at most 11, and four sessions busy at once can fill the pool and delay every sync route, including `/api/v1/health`. The default of 10 is a user decision; lower `CASCADASEN_SESSION_LOCK_MAX_WAITERS` (the web and MCP clients retry the busy 409) or raise the AnyIO thread limit if that happens. Rate limits and body checks run before the wait, so a refused request never waits. The lock is per process: across instances the store's conditional writes and `If-Match` stay the guard.

## 8. Limits and expiry

| Limit | Value | Setting |
|---|---|---|
| Request body on `/api/v1/sessions*` | 64 KB (413) | fixed |
| Session creation | 10 per hour per client IP (429 with `Retry-After`) | `CASCADASEN_RATE_CREATE_PER_HOUR` |
| Cut and repair | 30 per minute per session | `CASCADASEN_RATE_CUTS_PER_MINUTE` |
| Other edits and run commands | 60 per minute per session | `CASCADASEN_RATE_WRITES_PER_MINUTE` |
| SSE streams | 5 per session and client IP | `CASCADASEN_SSE_PER_SESSION_IP` |
| Requests in progress per session | 1 per backend process; up to 10 others wait up to 10 s, then 409 with `Retry-After: 1`; an eleventh waiter gets 409 at once | `CASCADASEN_SESSION_LOCK_TIMEOUT_S`, `CASCADASEN_SESSION_LOCK_MAX_WAITERS` |
| Added elements | 80 per session (buses + lines + loads + generators; each counts 1, so a substation with 6 lines and a load counts 8), 3000 MW each, 5000 MW of added load plus generation plus the MW changed by bus overrides; bus `load_mw`/`gen_mw`/`sync_mw` at most the base value + 3000 MW, `inertia_mws` at most 10 s × `sync_mw` | `domain/cascade/overlay.py` |
| Lines per cut call | 1 to 3 | |
| Runs per session | 20 (422 above) | |
| Session lifetime | 24 h after the last change | `CASCADASEN_SESSION_TTL_HOURS` |

Rate limits are counted per backend process, so with several instances the effective limit is per instance. The client IP is the `X-Forwarded-For` entry appended by the outermost trusted proxy, `CASCADASEN_TRUSTED_PROXY_HOPS` entries from the right (2 in production behind CloudFront and the ALB; entries further left are client-supplied and ignored). With the default 0, as in local dev, it is the peer address. The global runs `/api/v1/sim/runs*` (create, events, step, replay) share the 64 KB body cap and are limited to 60 commands per minute per client IP (`CASCADASEN_RATE_WRITES_PER_MINUTE`), because each command writes a run record.

Expiry: every write renews the 24 h. The memory and file stores treat older documents as gone. On S3 the bucket lifecycle expires objects after 1 day, and S3 rounds that to the next midnight UTC, so an idle session can live up to about 48 h there; `expires_at` in the document is the 24 h figure. A run record expires 24 h after its last command, even if its session lives on; reading it after that gives 404.

## 9. Error codes

Errors are JSON `{"detail": ...}` with a Spanish message (`ErrorResponse` in the spec). Input errors give `{"field", "message", "valid"?}`; body validation errors give FastAPI's list.

| Code | Meaning |
|---|---|
| 404 | Unknown or malformed session id, run not in this session, unknown element or line, unknown target |
| 409 | Deleting a base element (use `in_service: false`) or a bus that lines, loads or generators still use (`valid` lists them); finished run; another instance won the write (retry); the session stayed busy with another request for the lock timeout (10 s) or already had 10 requests waiting (retry after `Retry-After: 1`) |
| 412 | `If-Match` is not the current revision |
| 413 | Body over 64 KB |
| 422 | Invalid value (voltage not in the base set, `mw` out of range, `a == b`, unknown field, wrong role, `point` different from the session's), a limit reached |
| 429 | Rate limit or SSE slots; wait `Retry-After` seconds |

## 10. Physics rules

- The network view (`GET /{sid}/network`) has the shape of `GET /api/v1/sim/network` plus `origin` (`base`/`session`), `overridden` and `is_assumption` on nodes and lines, `loads`, `generators`, `out_of_service`, `warnings`, `balance` and `baseline {max_loading, overloaded, islands, load_shed_mw}`.
- **Rebalance (an assumption).** An edit changes generation minus load in its island. That difference is redispatched over the base synchronous units of the island in proportion to their synchronous MW; inertia does not change. A bus whose generation you set keeps it. Taking a bus out of service removes its load and generation, and its island redispatches the difference unless the outage splits the island. Each redispatch appears in `balance` with `is_assumption: true` and the rule text. It is not an optimal power flow.
- **Warnings**: `isolated_bus` (a bus with no line in service), `no_sync_to_redispatch` (nothing to redispatch, the island stays unbalanced), `unbalanced_island` (taking a line or bus out of service split an island; use the sandbox cut for splits).
- **The base case can overload.** A large datacenter can overload lines before any cut: on the real network, 300 MW at `B010` overloads 14 lines and sheds 373 MW in the baseline. Read `baseline` after each edit.
- Voltages are those of the base network (66, 110, 154, 220, 500 kV). `x_pu` defaults from the line length and voltage. Synchronous technologies (`hidro`, `termica`, `bioenergia`, `geotermica`) add inertia with H = 4 s by default (an assumption).
- Every value the session adds is an assumption and is labelled so (`is_assumption: true`, "supuesto (sesión)" in the UI).

## 11. Notice and guardrails

- Cut, repair and state return `notice: "Escenario hipotético: se modela el efecto, no el ataque."` Show it next to the result.
- The API models the effect of losing elements. No endpoint searches for, ranks or suggests the worst cut, and clients must not build one on top of it (for example by looping over every line to find the largest shed). The rate limits on cuts follow from this.
- Runs follow the guardrails of `docs/agents.md` section 3 and `docs/strategy.md`.
