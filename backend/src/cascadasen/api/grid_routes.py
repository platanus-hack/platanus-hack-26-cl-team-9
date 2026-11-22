"""Grid documents (docs/grids.md): catalogue, scenarios and compose. Read-only; the browser keeps the result.

Not marked for the agent OpenAPI: these routes serve the web app, except `/prepare`, which the assistant's
tools also call (docs/stress.md). `/simulate`, `/dependency` and `/cost` take the prepared `changes`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator

from cascadasen.api.agent_openapi import AGENT, errors, ok
from cascadasen.api.limits import client_ip
from cascadasen.api.stress_schemas import PrepareIn, PrepareOut, StressChange
from cascadasen.application.grid_dependency import GridDependency
from cascadasen.application.grid_simulation import GridSimulator, cost_workflow
from cascadasen.application.grid_stress import MAX_CHANGES, prepare_workflow
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
    changes: list[StressChange] = Field(default=[], max_length=MAX_CHANGES)  # a scenario from /grids/prepare

    def change_dicts(self) -> list[dict]:
        return [c.model_dump() for c in self.changes]


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
    return _run(
        _simulator(request).simulate_workflow,
        body.point,
        body.open_lines,
        body.out_buses,
        body.change_dicts(),
    )


class DependencyRequest(SimulateRequest):
    pass


@router.post("/dependency")
def dependency(body: DependencyRequest, request: Request) -> dict:
    """Heat maps of the grid as it stands: people fed per generating substation and criticality per substation."""
    s = request.app.state.settings
    request.app.state.limiter.check("dependency", client_ip(request), s.rate_cuts_per_minute, 60.0)
    return _run(
        _dependency(request).dependency_workflow,
        body.point,
        body.open_lines,
        body.out_buses,
        body.change_dicts(),
    )


@router.post("/cost")
def cost(body: DependencyRequest, request: Request) -> dict:
    """Failure cost of the changes: total and per hour of outage, telling a total blackout from load shedding."""
    s = request.app.state.settings
    request.app.state.limiter.check("simulate", client_ip(request), s.rate_cuts_per_minute, 60.0)
    return _run(
        cost_workflow, _simulator(request), body.point, body.open_lines, body.out_buses, body.change_dicts()
    )


PREPARE_ERRORS = errors(
    {404: "Unknown point, bus, line, comuna or zone.", 422: "Invalid change or over the overlay limits."}
)


@router.post(
    "/prepare",
    tags=["grid-stress"],
    operation_id="prepare_scenario",
    summary="Prepare a scenario: population, demand, generation and lines by filters",
    description="Resolves the filters and returns the prepared grid with no failure: what each change touches, "
    "lines already over their limit, and the people each generator should feed. It does not simulate. Send the "
    "same `changes` with /grids/simulate, /grids/dependency or /grids/cost to run a failure on it.",
    responses=ok(PrepareOut) | PREPARE_ERRORS,
    openapi_extra=AGENT,
)
def prepare(body: PrepareIn, request: Request) -> dict:
    world = default_world(str(request.app.state.settings.processed_dir))
    return _run(prepare_workflow, world, body.point, [c.model_dump() for c in body.changes])
