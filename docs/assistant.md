# In-app assistant: simulations in natural language

An endpoint of the backend where a user writes a request in natural language and an LLM runs the simulation by calling tools. The tools are the ones of the MCP server (`docs/mcp.md`), run through the app's own routes (`docs/sessions-api.md`). The MCP server serves an external client that brings its own LLM; the assistant is the same thing inside the application. It does not replace or change the theatre's bots (`docs/agents.md`).

Code: `api/assistant_routes.py`, `application/assistant.py`, `infrastructure/llm_tools.py`, `infrastructure/inprocess.py`, `mcp/{specs,toolbox}.py`. Tests: `tests/unit/{test_assistant,test_llm_tools,test_tool_specs}.py`, `tests/integration/test_assistant_api.py`.

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

## 4. Guardrails

Same as `cyber.md` section 8, `sessions-api.md` section 11 and `mcp.md` section 4.

- The tools are the MCP ones: none ranks or searches the worst cut, and `cut_lines` takes 1-3 lines. The system prompt repeats the rules (effects and prevention only, no attack technique, modelled values are assumptions) and tells the model that tool results and element names are data, never instructions. Names are free text written by whoever edits the session.
- It never plays the adversary and never reads the real state of a live run beyond what the tools return. This is a third LLM role, next to the after-action narrative and the C2 commander (`strategy.md` section 10): it carries out what the user asks on the user's own session.
- Results carry the scenario `notice`. Session and conversation ids are not logged.
- The API has no authentication, so cost is bounded only by the per-IP limit, the step cap and `maxTokens` 2000 per model call. A daily cap per IP is an open decision (`plan.md` section 9).

## 5. Not done

- Streaming (SSE) and the web UI: the response is one JSON document.
- Other providers (`anthropic`, `bedrock` Messages API).
- Terraform: the task role has no Bedrock permission and CloudFront keeps its default 30 s origin timeout (`infrastructure/iam.tf`, `cloudfront.tf`).
- Live test on 2026-11-21 against Bedrock and the 188-bus network with a bench of 17 turns in 5 conversations (edit and cut, strategic run with report and replay, guardrail, ambiguous requests, harder multi-step and prompt injection). `qwen.qwen3-next-80b-a3b` needed most of the guards above and still failed intermittently; `deepseek.v3.2` passed every check across several passes (the only flags were false negatives of the bench), with 1-19 s per message, and is the model set in the team's local `.env`. Other models that call tools through Converse on the account: `moonshotai.kimi-k2.5`, `zai.glm-5`, `mistral.mistral-large-3-675b-instruct`, `openai.gpt-oss-120b-1:0` (not benchmarked). The bench script is not in the repo.
