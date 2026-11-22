"""Grid documents (docs/grids.md): catalogue, scenarios and compose. Read-only; the browser keeps the result.

Not marked for the agent OpenAPI: these routes serve the web app, except `/prepare`, which the assistant's
tools also call (docs/stress.md). `/simulate`, `/dependency` and `/cost` take the prepared `changes`.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator

from cascadasen.api.agent_openapi import AGENT, errors, ok
from cascadasen.api.limits import client_ip
from cascadasen.api.stress_schemas import PlaceOut, PrepareIn, PrepareOut, SimulateOut, StressChange
from cascadasen.application.grid_dependency import GridDependency
from cascadasen.application.grid_simulation import GridSimulator, cost_workflow
from cascadasen.application.grid_stress import MAX_CHANGES, prepare_workflow, stress_context
from cascadasen.application.grids import GridComposer, GridError, catalog_workflow
from cascadasen.application.places import resolve_place
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
    """Failures to simulate on the default grid, optionally prepared with `changes`."""

    point: str = Field(
        description="Operating point id (feb2025-1500, feb2025-0300, nov2026-1300, nov2026-2000)."
    )
    open_lines: list[str] = Field(default=[], description="Lines out of service (R###).")
    out_buses: list[str] = Field(default=[], description="Substations out of service (B###).")
    changes: list[StressChange] = Field(
        default=[],
        max_length=MAX_CHANGES,
        description="A scenario from /grids/prepare, applied before the failures.",
    )

    def change_dicts(self) -> list[dict]:
        return [c.model_dump() for c in self.changes]


PREPARE_ERRORS = errors(
    {404: "Unknown point, bus, line, comuna or zone.", 422: "Invalid change or over the overlay limits."}
)


def _simulator(request: Request) -> GridSimulator:
    app = request.app
    if app.state.grid_sim is None:
        app.state.grid_sim = GridSimulator(default_world(str(app.state.settings.processed_dir)))
    return app.state.grid_sim


def grid_dependency(app: FastAPI) -> GridDependency:
    """The app's heat-map service, built on first use (a request or the startup warm-up)."""
    if app.state.grid_dependency is None:
        app.state.grid_dependency = GridDependency(default_world(str(app.state.settings.processed_dir)))
    return app.state.grid_dependency


def _dependency(request: Request) -> GridDependency:
    return grid_dependency(request.app)


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


@router.post(
    "/simulate",
    tags=["grid-stress"],
    operation_id="simulate_grid",
    summary="Simulate failures on the default grid, optionally prepared",
    description="Runs the cascade of the failures on the grid prepared with `changes`. It needs at least one line "
    "or substation out, or one change: with changes and no failure the cascade starts from the lines they overload. Returns the timeline, the direct loss and `supply`: per generating substation (by id) and per "
    "zone, the people it should feed before the failure against the people it still feeds.",
    responses=ok(SimulateOut) | PREPARE_ERRORS,
    openapi_extra=AGENT,
)
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
    criticality: bool = Field(
        default=True,
        description="False: only who feeds whom (gen_mw, people_fed, share_of_people), without the criticality "
        "of each substation, which runs one cascade per substation and is most of the time.",
    )


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
        criticality=body.criticality,
    )


@router.post("/cost")
def cost(body: SimulateRequest, request: Request) -> dict:
    """Failure cost of the changes: total and per hour of outage, telling a total blackout from load shedding."""
    s = request.app.state.settings
    request.app.state.limiter.check("simulate", client_ip(request), s.rate_cuts_per_minute, 60.0)
    return _run(
        cost_workflow, _simulator(request), body.point, body.open_lines, body.out_buses, body.change_dicts()
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


@router.get(
    "/places",
    tags=["grid-stress"],
    operation_id="resolve_place",
    summary="Find the substation a place resolves to",
    description="Resolves a place as a person names it (a substation, a comuna, a province or region, an area, or "
    "an id B###/A##) to one substation of the 188-bus network, with how it was resolved: a comuna goes to the "
    "substation that serves most of its people. The same rule as `places` in a change of /grids/prepare. Call it "
    "before adding a load or a generator to a session, so the element lands where the person meant.",
    responses=ok(PlaceOut)
    | errors({404: "Unknown place, or a comuna outside the SEN.", 422: "Empty place."}),
    openapi_extra=AGENT,
)
def place(
    request: Request,
    q: str = Query(min_length=1, max_length=120, description="The place.", examples=["Iquique"]),
    point: str = Query(
        "nov2026-1300",
        description="Operating point id (the network is the same at every point).",
        examples=["nov2026-1300"],
    ),
) -> dict:
    world = default_world(str(request.app.state.settings.processed_dir))
    return _run(lambda: resolve_place(stress_context(world, point), q))
