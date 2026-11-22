# In-app assistant: simulations in natural language

An endpoint of the backend where a user writes a request in natural language and an LLM runs the simulation by calling tools. The tools are the ones of the MCP server (`docs/mcp.md`), run through the app's own routes (`docs/sessions-api.md`). The MCP server serves an external client that brings its own LLM; the assistant is the same thing inside the application. It does not replace or change the theatre's bots (`docs/agents.md`).

Web client: `web/src/assistant/` (section 2c). Code: `api/assistant_routes.py`, `application/assistant.py`, `infrastructure/llm_tools.py`, `infrastructure/inprocess.py`, `mcp/{specs,toolbox}.py`. Tests: `tests/unit/{test_assistant,test_llm_tools,test_tool_specs}.py`, `tests/integration/test_assistant_api.py`.

## 1. Turn it on

Only Amazon Bedrock Converse is supported, with a model that supports tool use. Credentials come from the AWS chain, never from `.env` (see `backend/README.md`, LLM section).

```
CASCADASEN_LLM_ENABLED=true
CASCADASEN_LLM_PROVIDER=bedrock-converse
CASCADASEN_LLM_MODEL=<Bedrock model or inference-profile id>
CASCADASEN_AWS_REGION=us-east-1
```

Without them the other routes work as before and the assistant answers 503. Settings: `assistant_max_steps` (8 tool rounds per message), `assistant_deadline_s` (25 s, because CloudFront cuts a request at 30 s), `assistant_call_timeout_s` (20 s per Bedrock call), `assistant_history_messages` (30), `rate_assistant_per_minute` (10 per client IP). `CASCADASEN_LLM_MODEL` is shared with the C2 commander.

## 2. Routes (`/api/v1/assistant`)

| Method and path | Body | Response |
|---|---|---|
| `POST /chat` | `{message (1-2000 chars), conversation_id?, session_id?}` | `{conversation_id, session_id, run_id, reply, tool_calls: [{name, ok, result}], steps, truncated, notice}` |
| `GET /conversations/{cid}` | | `{conversation_id, session_id, run_id, turns, tool_calls}` |
| `DELETE /conversations/{cid}` | | 204. The session it worked on is kept |

```bash
curl -s -X POST localhost:8000/api/v1/assistant/chat -H 'content-type: application/json' \
  -d '{"message": "Agrega un datacenter de 120 MW en Antofagasta y dime si sobrecarga alguna línea"}'
curl -s -X POST localhost:8000/api/v1/assistant/chat -H 'content-type: application/json' \
  -d '{"message": "Ahora corta la línea R014", "conversation_id": "<conversation_id>"}'
```

`reply` is Spanish text. `truncated` is `"steps"` or `"deadline"` when a limit stopped the loop; the reply then says so, and a follow-up message such as "continúa" resumes from the stored history. Open `/?sesion=<session_id>` in the web app to see what the assistant changed.

| Code | Meaning |
|---|---|
| 404 | Unknown or expired conversation |
| 409 | Another message of the same conversation was running; retry |
| 413 | Body over 64 KB |
| 422 | Empty or long message, malformed id |
| 429 | Chat limit, with `Retry-After` |
| 502 | The model failed or does not support tools (fixed text, no provider detail). The user's turn is kept |
| 503 | LLM disabled or another provider |

## 2b. Streaming the steps (`POST /chat/stream`)

Same body as `/chat`; the answer is `text/event-stream` with each step as it happens, so a client can draw partial results on the map while the assistant works.

```
event: start
data: {"conversation_id": "…", "session_id": null, "run_id": null}

event: assistant_text
data: {"step": 1, "text": "Agrego el datacenter."}

event: tool_call
data: {"step": 1, "id": "t1", "name": "add_datacenter", "arguments": {"bus": "Antofagasta", "mw": 120}}

event: tool_result
data: {"step": 1, "id": "t1", "name": "add_datacenter", "ok": true, "result": {…}, "session_id": "…", "run_id": null}

: ping

event: done
data: {"conversation_id": "…", "session_id": "…", "run_id": "…", "reply": "…", "steps": 3, "truncated": null, "notice": "…"}
```

- `error` replaces `done` when the model fails or the conversation changed underneath (`{"status": 502|409|500, "detail"}`). Errors found before the stream starts (422, 404 conversation, 429, 503) are plain HTTP errors.
- Events are light: `result` is the same compact summary the model saw. To draw, fetch the full data the event points to: after `cut_lines` or `repair_lines`, `GET /api/v1/sessions/{sid}/state` (the cascade `timeline` with its frames); after `step`, `GET /api/v1/sessions/{sid}/runs/{rid}/snapshots?start=N` (`grid`, `transient`, `areas` per cycle); after an edit, `GET /api/v1/sessions/{sid}/network`. The session SSE (`GET /sessions/{sid}/events`) still reports each change too.
- `: ping` comments go out every `assistant_stream_ping_s` (10 s) without events, and the stream deadline is `assistant_stream_deadline_s` (90 s instead of 25 s), because CloudFront only cuts an origin that sends nothing for 30 s.
- The loop runs in a worker thread: if the client disconnects, it still finishes and saves the conversation.
- `EventSource` only does GET, so a browser reads this POST with `fetch` and a stream reader:

```js
const res = await fetch("/api/v1/assistant/chat/stream", {method: "POST",
  headers: {"Content-Type": "application/json"}, body: JSON.stringify({message, conversation_id})});
const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
let buf = "";
for (;;) {
  const {value, done} = await reader.read(); if (done) break;
  buf += value; let i;
  while ((i = buf.indexOf("\n\n")) >= 0) {
    const block = buf.slice(0, i); buf = buf.slice(i + 2);
    const kind = block.match(/^event: (.*)$/m)?.[1]; const data = block.match(/^data: (.*)$/m)?.[1];
    if (kind) onEvent(kind, JSON.parse(data));   // ": ping" blocks have no event line
  }
}
```

```bash
curl -N -X POST localhost:8000/api/v1/assistant/chat/stream -H 'content-type: application/json' \
  -d '{"message": "Agrega un datacenter de 120 MW en Antofagasta y corta R014"}'
```

## 2c. Web client (mapa 3, rail item **Asistente**)

The web reads `/chat/stream` and shows each step while the model works. It needs the backend with the LLM on (section 1); without it the first message gets 503 and the panel disables the input with "El asistente no está habilitado en este servidor."

| File (`web/src/assistant/`) | Role |
|---|---|
| `sse.ts` | `createSseParser(onEvent)`: chunks cut anywhere → `{event, data}`; skips `: ping`, accepts CRLF and multi-line `data:` |
| `steps.ts` | Pure chat state: `begin`, `reduce(state, event)` groups text and tool cards by `step` and pairs a `tool_result` with its `tool_call` by `id`; `interrupt`, `fail`, `annotate`, `fromConversation` |
| `labels.ts` | Spanish names for 23 of the 26 MCP tools (`list_incident_scenarios`, `start_incident_run` and `prepare_scenario` show their id), readable arguments, short result summaries, `refreshFor(tool)`, error texts per status |
| `assistantApi.ts` | `streamChat` (`fetch` + stream reader; `AssistantError` with `Retry-After` for errors before the stream; status 0 = network), `getConversation`, `deleteConversation` |
| `useAssistant.ts` | Hook owned by `CascadeApp`, so the chat survives view changes |
| `AssistantPanel.tsx`, `assistant.css` | The panel: history, tool cards (ejecutando… → ✓/✗, "Ver resultado" with the JSON), reply with the scenario `notice`, **Continuar** after a truncation, message box (1-2000 characters, Enter sends, Shift+Enter new line), **Nueva conversación** |

- **Which session.** Since #101 the web sends only `message` and `conversation_id` (`useAssistant.ts`, `streamChat` call in `send`) and does not join the session the assistant opens: the map does not follow it. The backend still accepts `session_id` in the request body (`ChatIn`, `api/assistant_routes.py`), and the web refreshes a session only when one is already joined (an **Incidentes** run). The text of this bullet before #101 had the web join the assistant's session and follow it through the session SSE.
- **Refresh.** After a successful tool whose `refreshFor` is not null (edits, `cut_lines`, `repair_lines`, `step`), the web reloads the session 300 ms later (`useSession.refresh`: document, network and `/state`) as a fallback to the SSE. After `step` it also fetches `GET /sessions/{sid}/runs/{rid}/snapshots?start=N` and only writes a one-line summary in the card ("3 instantáneas cargadas de la corrida (ciclos …)"): the web has no run viewer.
- **Persistence.** The conversation id is kept in `localStorage` under `sub50.assistant.cid` (wrapped in try/catch). On load the web rebuilds the chat with `GET /conversations/{cid}`; a 404 forgets the id. That route does not say which turn ran each tool and carries no `notice`, so a restored chat shows the replies, the earlier texts of each answer, and one collapsed list "Herramientas que ya usó esta conversación (N)". Restoring does not join the conversation's session (shared sessions are hidden, #101).
- **Errors.** Before the stream: 422 and 413 "El mensaje está vacío o supera 2000 caracteres.", 429 "Demasiados mensajes; espera N s." (from `Retry-After`), 404 forgets the id, 503 disables the chat. In the stream (`error`): 502 "El modelo falló; tu mensaje quedó guardado, intenta de nuevo.", 409 "Otro mensaje de esta conversación estaba corriendo; reintenta.", 500 generic. A stream that closes without `done` or `error` marks the turn interrupted and re-reads the conversation up to 5 times, 3 s apart, because the backend still finishes and saves it.
- **Guardrails.** The panel only shows what the tools returned. The summaries repeat fields of the result; the scenario `notice` (with the assumption note) is shown under each reply.
- Checked on 2026-11-21 against a local backend whose model was a scripted stand-in (the real app and routes, not Bedrock), with headless Chromium: live cards, `?sesion=` set, datacenter in Datos and cascade playing without reload, second message on the same session, chat restored after reload, **Nueva conversación** clearing it. Also with the stand-in: a run with `step` (snapshot summary on the card), the truncation notice with **Continuar**, the 502, 429 and 503 texts, and a stream cut before `tool_result` recovered by re-reading the conversation.
- Checked on 2026-11-22 against Bedrock (`deepseek.v3.2`) in the browser: the datacenter + R014 request (`start_session`, `add_datacenter`, `cut_lines`), a second message repairing R014 on the same session, reload, **Nueva conversación**, and a strategic run (`start_run`, `inject_event`, `step` of 3 cycles). The phone layout does not fit, as in the rest of mapa 3.

**Prepared scenarios.** When `prepare_scenario` returns, the web loads its `scenario` (point, changes, lines out, substations off) as the final grid of the map. It replaces what was there, and the timeline waits paused at 0. The chat stays open, and each added point gets a pin on the map (`stress.md` section 10). Checked on 2026-11-22 in headless Chromium against a local backend with a scripted stand-in model (no Bedrock credentials on the machine): a datacenter in Antofagasta and a solar plant in Iquique (pins at S/E ANTOFAGASTA and S/E CONDORES), a battery in Santiago added in a second message with the earlier changes resent (three pins), and "Marte" answered with the place error while the map kept its three points. Then checked on sub50.cl after the deploy (2026-11-22 05:48 UTC) with the real model: datacenter in Antofagasta, solar in Iquique, wind near Concepción plus batteries in Santiago in one message, nuclear in Mejillones (modelled as thermal, and said), a datacenter with no MW (it asked), and a four-turn conversation (datacenter in Puerto Montt, solar in Calama with the first change resent, cut R239 keeping both, "quita el datacenter" dropping only it). Every point landed at the expected substation, and the browser showed the pins with no console errors. Two flaws seen there were fixed next: the model opened a session before each map change, and it said "8 líneas sobrecargadas, las mismas que en la base" when the base had 1. Shared sessions are hidden from the web for now (#101): the panel no longer joins the assistant's session. See `docs/stress.md` section 7.

## 2d. One entry point to the grid, and the grid the user has (#130)

- **`prepare_scenario` is the only tool that changes the grid.** `add_substation` is now in `EXCLUDED` (`mcp/toolbox.py`): its edits went to a session the web does not show. A new substation is a change with `target: "substation"` (`docs/stress.md` section 4), so it flows through the same `changes` the web resends to `/grids/prepare`, `/grids/simulate`, `/grids/dependency` and `/grids/cost`, and the map pins it. The MCP server still offers `add_substation`.
- **The map is the source of truth.** `POST /chat` and `/chat/stream` take an optional `grid`: `{point, changes, open_lines, out_buses}`, the scenario on the map. The backend adds it to the system prompt of that message only (`grid_context` in `application/assistant.py`), with the order to ignore earlier changes of the history that are not in it. An empty grid says "Estado basal del punto …". The web sends it with every message (`gridRef` in `CascadeApp.tsx`, `getGrid` in `useAssistant.ts`), so clicking a scenario or a Benchmark condition (which empties the web's edits) restarts the assistant at baseline, and manual edits on the map are visible to it. A client that sends no `grid` gets the plain prompt, and in a shared session the web sends none.
- The model still sends the whole final grid in each `prepare_scenario`, now starting from the one in the prompt, not from its memory of the chat.

## 3. How it works

- `Assistant.chat` runs a loop: the model answers with text or tool calls, each call runs, the result goes back, until the model answers with text, `assistant_max_steps` is reached or `assistant_deadline_s` passes.
- A conversation is the document `assistant/<cid>.json` in the `DocumentStore` (memory, file or S3 like sessions, same 24 h TTL). It holds the messages in a provider-neutral format and the active `session_id` and `run_id`, so any backend instance continues it. Writes are conditional: if two messages of one conversation run at once, the second gets 409. The conversation id is a capability, like the session id.
- Tools run through `in_process_client`: an httpx client that enters the same FastAPI app by ASGI from the worker thread, with `X-Sub50-Agent: asistente`. The real routes validate, answer errors and enforce rate limits, keyed on the caller's IP (the transport presents it as the peer address), not on a shared loopback address. A chat message that makes many writes can therefore hit 429 inside a tool; the model sees the error and says so.
- Tool results are cut to 8 KB before they go back to the model. History is trimmed to the last 30 messages, starting at a user turn so no tool result loses its call.
- The user cannot run tools, so the first tool call that needs a session opens one automatically (its result carries a `nota`); this counts against the creation limit. The prompt tells the model never to ask the user to call a tool.
- `end_session` is not offered (the web has its own delete button) and `step` is capped at 24 cycles per call.
- **The assistant puts points, cuts and changes through `prepare_scenario` only** (since 2026-11-22). The web draws only that grid (sessions are hidden, #101), so a datacenter added with `add_datacenter` went into a session nobody saw and never reached the map. `EXCLUDED` in `mcp/toolbox.py` therefore leaves out `join_session`, `add_datacenter`, `add_generator`, `add_line`, `add_bus`, `edit_element`, `remove_element`, `reset_network`, `cut_lines`, `repair_lines` and `get_grid_state`; `describe_network`, the strategic runs and the incidents stay. The MCP server still offers every tool. A place goes in `places` as the user wrote it and resolves to the substation that serves it (`stress.md` section 3.1); the system prompt tells the model never to ask for an area or bus, to do every request of a message in the same turn, to resend earlier changes (each call replaces the map), and to say where each point went.
- A first `start_session` at the default point is deferred (`SessionTools.defers_session`): it answers `deferred: true` with a note and opens nothing, because the real model opened one before every map change and each counted against the per-IP creation limit. A tool that needs a session opens it on first use; `start_session` with another point (an incident's, e.g. `feb2025-1500`) opens one at once. The prepared summary carries `overloaded_lines_note`: the count has no base to compare with.
- `inject_event` or `submit_action` with no active run opens an `open_field` run first (its result says so), because a model that injected before `start_run` lost the event on the retry and then reported it as applied.
- **The model decides, the user does not size.** Until #125 `add_datacenter`, `add_generator`, `add_substation` and each `add` of a `prepare_scenario` change refused megawatts the user never typed (`stated`, `invented_adds`), so a non-technical user who said "you are the expert" was asked for numbers and the call failed. The guard and the `said` argument of `toolbox_for` are gone. The system prompt now tells the model to choose missing values (MW, place, technology) from `describe_network` data, execute, and say what it chose and that the value is its assumption (AGENTS.md section 4). It asks only when the request cannot be read or the technology does not exist.
- **Tool guide in the prompt** (#127). `TOOL_GUIDE` in `api/assistant_routes.py` says which tool answers which task: `describe_network` (with or without `focus`) for the health of the network, an area or a node; `prepare_scenario` to fail or change the grid and to measure the effect before and after a reinforcement; the run tools for events over time. The prompt no longer appends the whole MCP `INSTRUCTIONS` (it told the model to start with `start_session` and to use `add_datacenter`, `cut_lines` and others the assistant is not offered); it appends only `RULES` (`mcp/tools.py` now has `WORKFLOW` + `RULES` = `INSTRUCTIONS`, which the MCP server still sends whole). `test_the_system_prompt_only_names_tools_the_assistant_is_offered` fails if the prompt names a tool in `EXCLUDED`.
- If the model ends a turn promising an action ("la cortaré") with no tool call, no question and no offer ("dime…", "si quieres…"), the loop adds one hidden user message telling it to act now (`announces`, `NUDGE`). Hidden messages never appear in `GET /conversations/{cid}`.
- The deadline is predictive: a model call is not started when the elapsed time plus the mean duration of this message's calls would pass `assistant_deadline_s`.
- `tool_calls` in the response carries each call's `arguments`.
- `deepseek.v3.2` on Converse sometimes ends a text block with the start of its own tool-call markup (`<｜DSML｜function_calls`) next to a real `toolUse` block. `clean_text` in `infrastructure/llm_tools.py` cuts the text at the first `<｜…｜` marker, so the stream, the reply and the stored history stay clean. It also drops `<thinking>…</thinking>` (and `<think>`, `<reasoning>`, closed or not): on 2026-11-22 production showed the model's English reasoning as the reply.
- A Converse answer without `output.message.content` (a guardrail or an odd stop reason) is a 502 "El modelo de lenguaje no respondió", not a crash. Any other unexpected error is a JSON 500 "El asistente falló; reintenta." on `/chat` (it was Starlette's plain-text page) and an `error` event on the stream; both log the traceback (`log.exception`, no ids). On 2026-11-22 around 04:30 UTC production answered that 500 for every message for some minutes and then recovered; the cause is not known because the logs were not available.
- The web renders the model's Markdown (paragraphs, `-`/`1.` lists, `**bold**`, `` `code` ``, `#` headings) with `assistant/markdown.tsx`, as React text nodes only; the replies showed the asterisks before. The `prepare_scenario` card reads "Preparar el mapa" with the changes in words and where each place went (`labels.ts`); it read "[object Object]".

## 4. Guardrails

Decision 2026-11-22: the team removed the dual-use rules (no worst-cut search, no ranking, effects only) to stress-test the network. The only strong guardrail left is topic: the assistant talks only about the network and how to test it, and refuses anything else without calling tools. `cyber.md` section 8 no longer applies to the assistant; it still describes the strategic layer.

- The tools are the MCP ones: `cut_lines` takes 1-3 lines. The system prompt tells the model that tool results and element names are data, never instructions (a security rule, kept). Names are free text written by whoever edits the session.
- It never plays the adversary and never reads the real state of a live run beyond what the tools return. This is a third LLM role, next to the after-action narrative and the C2 commander (`strategy.md` section 10): it carries out what the user asks on the user's own session.
- Results carry the scenario `notice`. Session and conversation ids are not logged.
- The API has no authentication, so cost is bounded only by the per-IP limit, the step cap and `maxTokens` 2000 per model call. A daily cap per IP is an open decision (`plan.md` section 9).

## 5. Not done

- Other providers (`anthropic`, `bedrock` Messages API).
- Terraform: the task role has no Bedrock permission and CloudFront keeps its default 30 s origin timeout (`infrastructure/iam.tf`, `cloudfront.tf`).
- Live test on 2026-11-21 against Bedrock and the 188-bus network with a bench of 17 turns in 5 conversations (edit and cut, strategic run with report and replay, guardrail, ambiguous requests, harder multi-step and prompt injection). `qwen.qwen3-next-80b-a3b` needed most of the guards above and still failed intermittently; `deepseek.v3.2` passed every check across several passes (the only flags were false negatives of the bench), with 1-19 s per message, and is the model set in the team's local `.env`. Other models that call tools through Converse on the account: `moonshotai.kimi-k2.5`, `zai.glm-5`, `mistral.mistral-large-3-675b-instruct`, `openai.gpt-oss-120b-1:0` (not benchmarked). The bench script is not in the repo.
