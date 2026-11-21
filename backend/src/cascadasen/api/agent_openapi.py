"""Agent-only OpenAPI spec (docs/openapi.md): the routes marked with `AGENT`, served at
`GET /api/v1/agents/openapi.json` and versioned in `docs/openapi/agents.openapi.json`.

Regenerate the file: `cd backend && uv run python -m cascadasen.api.agent_openapi`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from fastapi.routing import RouteContext, iter_route_contexts
from pydantic import BaseModel, Field

AGENT: dict[str, Any] = {"x-sub50-agent": True}  # openapi_extra of every agent route
SPEC_URL = "/api/v1/agents/openapi.json"
SPEC_FILE = Path(__file__).resolve().parents[4] / "docs" / "openapi" / "agents.openapi.json"

TITLE = "Sub50 agent API"
VERSION = "1.0.0"
DESCRIPTION = """\
Endpoints an external agent needs to run strategic experiments on Sub50, a simulator of
blackouts in the Chilean national grid (SEN). Public base URL: `https://sub50.cl`.

**Ids.** The network has buses `B###` and lines `R###` (`GET /api/v1/sim/network`). Event targets
also accept an area (`A06`), a zone (`NG`), a corridor (`A06-A07/500`), a defence function
(`pdce_zn`) or a real substation id (`SE...`). Event types, policies, objectives and templates come
from `GET /api/v1/sim/catalog`. A run is identified by the `run_id` returned on creation.

**Runs.** Runs in `global-runs` work on the default dataset and live in server memory: the most
recent 100 are kept and any run can be rebuilt from its recipe (`GET .../trace`). Session
endpoints (tags `sessions`, `session-network`, `session-sandbox`, `session-runs`) carry the
session id in the path and work on that session's private copy of the dataset; create a session
first and pass its id to every session call.

**Notice.** Every scenario is hypothetical and simulated: Sub50 models the consequence of an
event on the grid, never the attack technique. The catalog and every run summary carry a
`notice` field saying so.

Errors return `{"detail": ...}`; messages inside `detail` are in Spanish.
"""

TAGS = {
    "sessions": "Create, read and delete a session: a private, editable copy of the default dataset.",
    "session-network": "Read and edit a session's network: buses, lines, loads and generators.",
    "session-sandbox": "Cut and repair lines in a session and read the resulting state.",
    "session-runs": "Strategic runs over a session's network.",
    "catalog": "What an agent can choose from: events, actions, policies, objectives, templates.",
    "global-runs": "Strategic runs over the default dataset, and its network.",
}


class ErrorResponse(BaseModel):
    """Error body shared by every agent route."""

    detail: str | dict[str, Any] | list[dict[str, Any]] = Field(
        description=(
            "Spanish message. Input errors from the simulator give an object `{field, message, "
            "valid}`; request validation errors give FastAPI's list of `{loc, msg, type}`."
        ),
        examples=["No existe la corrida: 3f2a9c1b7d4e"],
    )


def errors(codes: dict[int, str]) -> dict[int | str, dict[str, Any]]:
    """`responses=` entry: each status code with its one-line description and `ErrorResponse`."""
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes.items()}


def agent_routes(app: FastAPI) -> list[RouteContext]:
    """Marked routes, including those of included routers (FastAPI keeps them nested)."""
    return [
        r
        for r in iter_route_contexts(app.routes)
        if (getattr(r, "openapi_extra", None) or {}).get("x-sub50-agent")
    ]


def agent_openapi(app: FastAPI) -> dict[str, Any]:
    routes = agent_routes(app)
    used = {tag for r in routes for tag in r.tags or ()}
    return get_openapi(
        title=TITLE,
        version=VERSION,
        description=DESCRIPTION,
        routes=routes,
        tags=[{"name": name, "description": text} for name, text in TAGS.items() if name in used],
    )


def mount(app: FastAPI) -> None:
    """Serve the agent spec and a Swagger page for it (/api/v1/agents/docs)."""

    @app.get(SPEC_URL, include_in_schema=False)
    def agents_openapi() -> dict[str, Any]:
        if getattr(app.state, "agent_openapi", None) is None:
            app.state.agent_openapi = agent_openapi(app)
        return app.state.agent_openapi

    @app.get("/api/v1/agents/docs", include_in_schema=False)
    def agents_docs() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url=SPEC_URL, title=TITLE)


def dumps(spec: dict[str, Any]) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    from cascadasen.api.app import create_app

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else SPEC_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(agent_openapi(create_app())), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
