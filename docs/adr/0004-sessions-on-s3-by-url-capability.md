# 0004. Sessions are JSON documents on S3, the session id is the capability
Status: Accepted (2026-11-21)

## Context
Several people and external agents work on the same what-if network at once. The demo has no accounts, and the service runs as one ECS task with no database (`infrastructure.md`).

## Decision
- A session is an overlay over the 188-bus network (added buses, lines, loads, generators, overrides) stored as one JSON document `sessions/<sid>.json`. The base dataset never changes. Runs are nested under the session and persisted.
- The store is behind the `DocumentStore` port with memory, file and S3 adapters (`CASCADASEN_SESSION_STORE`). Writes are conditional (`if_match`, `if_none_match`). A lost race raises `ConflictError`, retried 3 times, then the API answers 409.
- There is no API key and no cookie. The session id is the capability: whoever has it can read and edit the session. The browser shares it as `?sesion=<sid>`.
- Sessions and run records expire 24 h after their last change. Changes reach other clients through SSE with a polling fallback (`ETag` and `If-None-Match`).

## Consequences
- Anyone with the link can edit. The id must not be published.
- Several backend instances can serve one session, and the sessions bucket lifecycle cleans up objects. S3 rounds expiry to the next UTC midnight, so an idle session can live about 48 h on S3. The app enforces the 24 h itself.
- No database to run or migrate.
- The API has per-client rate limits and a request body limit (`api/limits.py`), because the id is the only protection.

## Sources
`docs/sessions-api.md` sections 1 and 7 and its expiry paragraph, `docs/plan.md` section 9 decision 14, `docs/infrastructure.md` ("Sessions bucket"), `docs/architecture.md` section 2.1 (`DocumentStore`).
