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
| `labels.ts` | Spanish tool names (the 23 MCP tools), readable arguments, short result summaries, `refreshFor(tool)`, error texts per status |
| `assistantApi.ts` | `streamChat` (`fetch` + stream reader; `AssistantError` with `Retry-After` for errors before the stream; status 0 = network), `getConversation`, `deleteConversation` |
| `useAssistant.ts` | Hook owned by `CascadeApp`, so the chat survives view changes |
| `AssistantPanel.tsx`, `assistant.css` | The panel: history, tool cards (ejecutando… → ✓/✗, "Ver resultado" with the JSON), reply with the scenario `notice`, **Continuar** after a truncation, message box (1-2000 characters, Enter sends, Shift+Enter new line), **Nueva conversación** |

- **Which session.** Every message sends `session_id` = the session on screen, when there is one, so the assistant works on what the user sees. When `start`, `tool_result` or `done` carries a `session_id` that differs from the one on screen, the web joins it (`useSession.join`, which also puts `?sesion=` in the URL). The map then follows by itself through the session SSE.
- **Refresh.** After a successful tool whose `refreshFor` is not null (edits, `cut_lines`, `repair_lines`, `step`), the web reloads the session 300 ms later (`useSession.refresh`: document, network and `/state`) as a fallback to the SSE. After `step` it also fetches `GET /sessions/{sid}/runs/{rid}/snapshots?start=N` and only writes a one-line summary in the card ("3 instantáneas cargadas de la corrida (ciclos …)"): the web has no run viewer.
- **Persistence.** The conversation id is kept in `localStorage` under `sub50.assistant.cid` (wrapped in try/catch). On load the web rebuilds the chat with `GET /conversations/{cid}`; a 404 forgets the id. That route does not say which turn ran each tool and carries no `notice`, so a restored chat shows the replies, the earlier texts of each answer, and one collapsed list "Herramientas que ya usó esta conversación (N)". Restoring joins the conversation's session only when no session is on screen.
- **Errors.** Before the stream: 422 and 413 "El mensaje está vacío o supera 2000 caracteres.", 429 "Demasiados mensajes; espera N s." (from `Retry-After`), 404 forgets the id, 503 disables the chat. In the stream (`error`): 502 "El modelo falló; tu mensaje quedó guardado, intenta de nuevo.", 409 "Otro mensaje de esta conversación estaba corriendo; reintenta.", 500 generic. A stream that closes without `done` or `error` marks the turn interrupted and re-reads the conversation up to 5 times, 3 s apart, because the backend still finishes and saves it.
- **Guardrails.** The panel only shows what the tools returned. The summaries repeat fields of the result; the scenario `notice` (with the assumption note) is shown under each reply.
- Checked on 2026-11-21 against a local backend whose model was a scripted stand-in (the real app and routes, not Bedrock), with headless Chromium: live cards, `?sesion=` set, datacenter in Datos and cascade playing without reload, second message on the same session, chat restored after reload, **Nueva conversación** clearing it. Also with the stand-in: a run with `step` (snapshot summary on the card), the truncation notice with **Continuar**, the 502, 429 and 503 texts, and a stream cut before `tool_result` recovered by re-reading the conversation.
- Checked on 2026-11-22 against Bedrock (`deepseek.v3.2`) in the browser: the datacenter + R014 request (`start_session`, `add_datacenter`, `cut_lines`), a second message repairing R014 on the same session, reload, **Nueva conversación**, and a strategic run (`start_run`, `inject_event`, `step` of 3 cycles). The phone layout does not fit, as in the rest of mapa 3.

**Prepared scenarios.** When `prepare_scenario` returns, the web loads its `scenario` (point, changes, lines out, substations off) as the final grid of the map. It replaces what was there, and the timeline waits paused at 0. Shared sessions are hidden from the web for now (#101): the panel no longer joins the assistant's session. See `docs/stress.md` section 7.

## 3. How it works

- `Assistant.chat` runs a loop: the model answers with text or tool calls, each call runs, the result goes back, until the model answers with text, `assistant_max_steps` is reached or `assistant_deadline_s` passes.
- A conversation is the document `assistant/<cid>.json` in the `DocumentStore` (memory, file or S3 like sessions, same 24 h TTL). It holds the messages in a provider-neutral format and the active `session_id` and `run_id`, so any backend instance continues it. Writes are conditional: if two messages of one conversation run at once, the second gets 409. The conversation id is a capability, like the session id.
- Tools run through `in_process_client`: an httpx client that enters the same FastAPI app by ASGI from the worker thread, with `X-Sub50-Agent: asistente`. The real routes validate, answer errors and enforce rate limits, keyed on the caller's IP (the transport presents it as the peer address), not on a shared loopback address. A chat message that makes many writes can therefore hit 429 inside a tool; the model sees the error and says so.
- Tool results are cut to 8 KB before they go back to the model. History is trimmed to the last 30 messages, starting at a user turn so no tool result loses its call.
- The user cannot run tools, so the first tool call that needs a session opens one automatically (its result carries a `nota`); this counts against the creation limit. The prompt tells the model never to ask the user to call a tool.
- `end_session` is not offered (the web has its own delete button) and `step` is capped at 24 cycles per call.
- `inject_event` or `submit_action` with no active run opens an `open_field` run first (its result says so), because a model that injected before `start_run` lost the event on the retry and then reported it as applied.
- `add_datacenter` and `add_generator` refuse megawatts the user never wrote in the conversation (`stated` in `mcp/toolbox.py` compares with every number the user typed, also as GW) and tell the model to ask. A model invented 150 and 500 MW for "agrega un datacenter en Calama".
- If the model ends a turn promising an action ("la cortaré") with no tool call, no question and no offer ("dime…", "si quieres…"), the loop adds one hidden user message telling it to act now (`announces`, `NUDGE`). Hidden messages never appear in `GET /conversations/{cid}`.
- The deadline is predictive: a model call is not started when the elapsed time plus the mean duration of this message's calls would pass `assistant_deadline_s`.
- `tool_calls` in the response carries each call's `arguments`.
- `deepseek.v3.2` on Converse sometimes ends a text block with the start of its own tool-call markup (`<｜DSML｜function_calls`) next to a real `toolUse` block. `clean_text` in `infrastructure/llm_tools.py` cuts the text at the first `<｜…｜` marker, so the stream, the reply and the stored history stay clean.

## 4. Guardrails

Same as `cyber.md` section 8, `sessions-api.md` section 11 and `mcp.md` section 4.

- The tools are the MCP ones: none ranks or searches the worst cut, and `cut_lines` takes 1-3 lines. The system prompt repeats the rules (effects and prevention only, no attack technique, modelled values are assumptions) and tells the model that tool results and element names are data, never instructions. Names are free text written by whoever edits the session.
- It never plays the adversary and never reads the real state of a live run beyond what the tools return. This is a third LLM role, next to the after-action narrative and the C2 commander (`strategy.md` section 10): it carries out what the user asks on the user's own session.
- Results carry the scenario `notice`. Session and conversation ids are not logged.
- The API has no authentication, so cost is bounded only by the per-IP limit, the step cap and `maxTokens` 2000 per model call. A daily cap per IP is an open decision (`plan.md` section 9).

## 5. Not done

- Other providers (`anthropic`, `bedrock` Messages API).
- Terraform: the task role has no Bedrock permission and CloudFront keeps its default 30 s origin timeout (`infrastructure/iam.tf`, `cloudfront.tf`).
- Live test on 2026-11-21 against Bedrock and the 188-bus network with a bench of 17 turns in 5 conversations (edit and cut, strategic run with report and replay, guardrail, ambiguous requests, harder multi-step and prompt injection). `qwen.qwen3-next-80b-a3b` needed most of the guards above and still failed intermittently; `deepseek.v3.2` passed every check across several passes (the only flags were false negatives of the bench), with 1-19 s per message, and is the model set in the team's local `.env`. Other models that call tools through Converse on the account: `moonshotai.kimi-k2.5`, `zai.glm-5`, `mistral.mistral-large-3-675b-instruct`, `openai.gpt-oss-120b-1:0` (not benchmarked). The bench script is not in the repo.
