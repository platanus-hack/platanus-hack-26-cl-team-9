# 0005. Hexagonal layering, enforced by a test
Status: Accepted. The test was added 2026-11-22.

## Context
The backend has a pure simulation core, public data adapters, an HTTP API, an MCP server and an assistant that calls the API. Without a rule, core code would start importing adapters and the physics could not be tested without a network.

## Decision
Ports and adapters (`architecture.md` section 2):
- `api/` calls `application/`, which calls `domain/`. `infrastructure/` implements the ports of `domain/ports.py` and wires them in `container.py`.
- `domain/` imports nothing from `api`, `application`, `infrastructure`, `mcp`, `cli` or `sim_fixtures`. `application/` and `infrastructure/` import neither `api` nor `mcp`.
- `backend/tests/unit/test_architecture.py` parses the imports with `ast` and fails on a new violation. It also fails on a module cycle among top-level imports.

## Consequences
- Six `application` to `infrastructure` imports exist today (CLI `main()` entry points and the default document store of `run_experiment`). They are listed in `KNOWN_EXCEPTIONS` in the test. A new one fails the test.
- `api` imports `mcp` in four places (the assistant reuses the MCP tool functions). The test does not check this edge.
- Removing the known exceptions means moving the entry points into the composition root. That is a larger refactor.
- Adding a data source is one adapter plus a line in `container.py`.

## Sources
`docs/architecture.md` section 2 (dependency rule, ports), `backend/tests/unit/test_architecture.py`.
