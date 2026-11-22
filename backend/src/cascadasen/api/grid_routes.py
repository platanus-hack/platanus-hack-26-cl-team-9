"""Grid documents (docs/grids.md): catalogue, scenarios and compose. Read-only; the browser keeps the result.

Not marked for the agent OpenAPI: these routes serve the web app.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, model_validator

from cascadasen.application.grids import GridComposer, GridError, catalog_workflow
from cascadasen.infrastructure.container import grid_store

router = APIRouter(prefix="/api/v1/grids", tags=["grids"])
_STATUS = {"not_found": 404, "invalid": 422, "unavailable": 503}


class ComposeRequest(BaseModel):
    point: str | None = None
    scenario: str | None = None
    context: list[str] | None = None  # context documents to include; omitted: all

    @model_validator(mode="after")
    def _one_of(self) -> ComposeRequest:
        if bool(self.point) == bool(self.scenario):
            raise ValueError("indica `point` o `scenario`, no ambos")
        return self


def _composer(request: Request) -> GridComposer:
    app = request.app
    if app.state.grids is None:
        app.state.grids = GridComposer(grid_store(app.state.settings))
    return app.state.grids


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except GridError as exc:
        raise HTTPException(_STATUS[exc.kind], str(exc)) from exc


@router.get("/sources")
def sources(request: Request) -> dict:
    return _run(catalog_workflow, _composer(request).store)


@router.get("/scenarios")
def scenarios(request: Request) -> list[dict]:
    return _run(catalog_workflow, _composer(request).store)["scenarios"]


@router.post("/compose")
def compose(body: ComposeRequest, request: Request) -> dict:
    return _run(_composer(request).compose_workflow, body.point, body.scenario, body.context)


@router.get("/documents/{key:path}")
def document(key: str, request: Request) -> Response:
    data = _run(_composer(request).document_workflow, key)
    return Response(data, media_type="application/json")
