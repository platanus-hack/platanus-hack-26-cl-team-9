"""Grid documents (docs/grids.md): catalogue, scenarios and compose. Read-only; the browser keeps the result.

Not marked for the agent OpenAPI: these routes serve the web app.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, model_validator

from cascadasen.api.limits import client_ip
from cascadasen.application.grid_dependency import GridDependency
from cascadasen.application.grid_simulation import GridSimulator
from cascadasen.application.grids import GridComposer, GridError, catalog_workflow
from cascadasen.application.theater_world import default_world
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


class SimulateRequest(BaseModel):
    point: str
    open_lines: list[str] = []
    out_buses: list[str] = []


def _simulator(request: Request) -> GridSimulator:
    app = request.app
    if app.state.grid_sim is None:
        app.state.grid_sim = GridSimulator(default_world(str(app.state.settings.processed_dir)))
    return app.state.grid_sim


def _dependency(request: Request) -> GridDependency:
    app = request.app
    if app.state.grid_dependency is None:
        app.state.grid_dependency = GridDependency(default_world(str(app.state.settings.processed_dir)))
    return app.state.grid_dependency


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


@router.post("/simulate")
def simulate(body: SimulateRequest, request: Request) -> dict:
    s = request.app.state.settings
    request.app.state.limiter.check("simulate", client_ip(request), s.rate_cuts_per_minute, 60.0)
    return _run(_simulator(request).simulate_workflow, body.point, body.open_lines, body.out_buses)


class DependencyRequest(BaseModel):
    point: str
    open_lines: list[str] = []
    out_buses: list[str] = []


@router.post("/dependency")
def dependency(body: DependencyRequest, request: Request) -> dict:
    """Heat maps of the grid as it stands: people fed per generating substation and criticality per substation."""
    s = request.app.state.settings
    request.app.state.limiter.check("dependency", client_ip(request), s.rate_cuts_per_minute, 60.0)
    return _run(_dependency(request).dependency_workflow, body.point, body.open_lines, body.out_buses)
