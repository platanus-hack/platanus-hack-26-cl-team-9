"""HTTP routes of the simulation API: reduced network, physical contingencies, strategic runs and
campaigns (docs/stack.md 7 and 7.1). Mounted by `create_app`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse

from cascadasen.api.agent_openapi import AGENT, errors, ok
from cascadasen.api.limits import client_ip
from cascadasen.api.simulation_schemas import (
    AfterActionOut,
    CampaignIn,
    CatalogOut,
    EventIn,
    NetworkOut,
    ReplayIn,
    RunCreate,
    RunEventOut,
    RunReportOut,
    RunSnapshotsOut,
    RunStateOut,
    RunStepOut,
    RunSummary,
    RunTraceOut,
    SimulateRequest,
    StepIn,
    TheaterNetworkOut,
)
from cascadasen.application.run_campaign import CampaignNotFoundError, CampaignSpec
from cascadasen.application.run_experiment import RunCache, RunConflictError, RunNotFoundError, run_config
from cascadasen.application.simulate import SimulateCommand, SimulationInputError, SimulationTimeoutError
from cascadasen.application.simulation_service import SimulationService
from cascadasen.application.theater_world import default_world
from cascadasen.domain.theater.cycle import AdversaryConfig, RunFinishedError, RunInputError
from cascadasen.domain.theater.narrative import templates
from cascadasen.infrastructure.llm import llm_adapters

router = APIRouter(prefix="/api/v1")


def get_simulation(request: Request) -> SimulationService:
    sim = request.app.state.simulation
    if sim is None:
        service = request.app.state.service
        if service is None:
            raise HTTPException(503, "No hay snapshot de la red. Ejecuta `cascadasen-build` primero.")
        settings = request.app.state.settings
        interpreter, advisor = llm_adapters(settings)
        world = default_world(str(settings.processed_dir))
        sim = SimulationService.from_snapshot(
            service.s,
            interpreter=interpreter,
            advisor=advisor,
            world=world,
            store=request.app.state.store,
            run_cache=RunCache(settings.run_cache_size),
            version=settings.version,
        )
        request.app.state.simulation = sim
    return sim


Sim = Annotated[SimulationService, Depends(get_simulation)]


def global_run_limit(request: Request) -> None:
    """Every global run command writes a record (an S3 PUT in production): limited per client IP."""
    s = request.app.state.settings
    request.app.state.limiter.check("global_runs", client_ip(request), s.rate_writes_per_minute, 60.0)


RATE_LIMITED = [Depends(global_run_limit)]
TOO_MANY = {429: "Rate limit reached (per client IP); wait the seconds in Retry-After."}
RunId = Annotated[
    str,
    Path(
        description="Run id returned by `POST /api/v1/sim/runs` or `/replay` (12 hex characters)",
        examples=["3f2a9c1b7d4e"],
    ),
]


def input_error(exc: SimulationInputError) -> HTTPException:
    return HTTPException(422, exc.detail())


@router.get(
    "/simulate/network",
    response_model=NetworkOut,
    tags=["simulación"],
    summary="Áreas y corredores de la red de 13 áreas de POST /simulate",
)
def network(sim: Sim) -> dict[str, Any]:
    return sim.network_view()


@router.get(
    "/sim/network",
    tags=["global-runs"],
    operation_id="global_get_network",
    summary="Read the default 188-bus network with its areas, corridors and defences",
    description=(
        "Returns the mapa 3 network of the default dataset at one operating point: `nodes` (buses "
        "`B###` with their `area`), `lines` (`R###` with their `corridor`), `buses` (generation, load, "
        "people), `areas`, `corridors` and `defenses`. Call it before creating a run or injecting an "
        "event to pick valid targets. Read only."
    ),
    responses=ok(TheaterNetworkOut)
    | errors(
        {
            404: "Unknown operating point; `detail.valid` lists the valid ones.",
            422: "Invalid query parameter.",
        }
    ),
    openapi_extra=AGENT,
)
def theater_network(
    sim: Sim,
    point: Annotated[
        str | None,
        Query(
            description="Operating point id; omitted means the reference point. Valid ids are in the 404 body.",
            examples=["nov2026-1300"],
        ),
    ] = None,
) -> dict[str, Any]:
    try:
        return sim.theater_network(point)
    except KeyError as exc:
        raise HTTPException(
            404, {"field": "point", "message": "punto de operación desconocido", "valid": sim.world.points()}
        ) from exc


@router.post(
    "/simulate",
    tags=["simulación"],
    summary="Una contingencia física sobre la red reducida → timeline.json (stack.md 6)",
    response_description="timeline.json: events, frames, summary (L0-L3, personas, MWh, costo), provenance",
)
def simulate(sim: Sim, body: SimulateRequest) -> Any:
    cmd = SimulateCommand(
        scenario=body.scenario,
        defenses=body.defenses,
        behavior=body.behavior,
        elements_out=body.elements_out,
        battery_mw=body.battery_mw,
        group_out=[g.model_dump() for g in body.group_out],
        defenses_disabled=body.defenses_disabled,
        outage_duration_h=body.outage_duration_h,
        cause=body.cause,
        frames=body.frames,
    )
    try:
        return sim.simulate(cmd)
    except SimulationInputError as exc:
        raise input_error(exc) from exc
    except SimulationTimeoutError:
        return JSONResponse({"reason": "timeout"}, status_code=503)


# ------------------------------------------------------------------ strategic runs (stack.md 7.1)


def run_call(fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except RunNotFoundError as exc:
        raise HTTPException(404, f"No existe la corrida: {exc.args[0]}") from exc
    except RunInputError as exc:
        raise HTTPException(404 if exc.not_found else 422, exc.detail()) from exc
    except RunFinishedError as exc:
        raise HTTPException(409, "La corrida terminó; usa /replay para repetirla") from exc
    except RunConflictError as exc:
        raise HTTPException(409, "La corrida cambió en otra instancia; reintenta") from exc
    except CampaignNotFoundError as exc:
        raise HTTPException(404, f"No existe la campaña: {exc.args[0]}") from exc


@router.get(
    "/sim/catalog",
    tags=["catalog"],
    operation_id="get_catalog",
    summary="List event types, actions, policies, objectives and experiment templates",
    description=(
        "Returns every choice an agent can make: `events` (type ids for `inject_run_event` and the "
        "target kinds they accept), defensive `actions`, `policies` A/B/C, adversary `objectives`, "
        "missions and experiment `templates`. Call it once before creating runs. Read only."
    ),
    responses=ok(CatalogOut),
    openapi_extra=AGENT,
)
def sim_catalog(sim: Sim) -> dict[str, Any]:
    return sim.catalog()


@router.post(
    "/sim/runs",
    response_model=RunSummary,
    status_code=201,
    tags=["global-runs"],
    operation_id="global_create_run",
    summary="Create a strategic run over the default dataset",
    description=(
        "Creates a run of the strategic theatre from a template (`GET /api/v1/sim/catalog` → "
        "`templates`) with a policy, an optional adversary, uncertainty, seed and initial events. "
        "Returns the run summary with its `run_id`, used by every other run call. With `auto_run` "
        "the run is played to the end before returning. The run is persisted for 24 hours after its "
        "last command and rebuilt from its recipe when the server no longer holds it."
    ),
    responses=errors(
        {
            404: "Unknown template or event target.",
            422: "Invalid input (policy, operating point, horizon, adversary, capabilities, event type).",
            **TOO_MANY,
        }
    ),
    dependencies=RATE_LIMITED,
    openapi_extra=AGENT,
)
def create_run(sim: Sim, body: RunCreate) -> dict[str, Any]:
    data = body.model_dump(exclude={"auto_run"})
    data["initial_events"] = [e.model_dump() for e in body.initial_events]
    return run_call(lambda: sim.runs.create(run_config(data), body.auto_run))


@router.get(
    "/sim/runs/{run_id}",
    tags=["global-runs"],
    operation_id="global_get_run",
    summary="Read a run's latest state",
    description=(
        "Returns the run summary, the latest cycle snapshot (real, observed and per-agent estimated "
        "state, decisions, grid frame, areas, crews, metrics), the resource ledger and the metric "
        "series of every cycle so far. Read only."
    ),
    responses=ok(RunStateOut) | errors({404: "Unknown run_id.", 422: "Invalid path parameter."}),
    openapi_extra=AGENT,
)
def get_run(sim: Sim, run_id: RunId) -> dict[str, Any]:
    return run_call(sim.runs.state, run_id)


@router.post(
    "/sim/runs/{run_id}/events",
    tags=["global-runs"],
    operation_id="global_inject_run_event",
    summary="Trigger an event on a target; it applies at the next cycle",
    description=(
        "Queues an event (`type` from `GET /api/v1/sim/catalog` → `events`) on a target: area, zone, "
        "corridor, bus `B###`, line `R###`, defence function or real substation id `SE...`. The "
        "response echoes `resolved_target` and `area`. The event is logged with `source: user` and "
        "takes effect when the run is stepped."
    ),
    responses=ok(RunEventOut)
    | errors(
        {
            404: "Unknown run_id or target.",
            409: "The run has finished; replay it instead.",
            422: "Invalid event type or body.",
            **TOO_MANY,
        }
    ),
    dependencies=RATE_LIMITED,
    openapi_extra=AGENT,
)
def inject_event(sim: Sim, run_id: RunId, body: EventIn) -> dict[str, Any]:
    return run_call(sim.runs.inject, run_id, body.type, body.target, body.params, body.cause)


@router.post(
    "/sim/runs/{run_id}/step",
    tags=["global-runs"],
    operation_id="global_step_run",
    summary="Advance a run by n cycles of 5 minutes",
    description=(
        "Runs `cycles` cycles (1 to 72) and returns one snapshot per cycle. Queued events apply in "
        "the first one. A finished run returns no new snapshots."
    ),
    responses=ok(RunStepOut) | errors({404: "Unknown run_id.", 422: "`cycles` outside 1-72.", **TOO_MANY}),
    dependencies=RATE_LIMITED,
    openapi_extra=AGENT,
)
def step_run(sim: Sim, run_id: RunId, body: StepIn) -> dict[str, Any]:
    return run_call(sim.runs.step, run_id, body.cycles)


@router.post(
    "/sim/runs/{run_id}/replay",
    response_model=RunSummary,
    status_code=201,
    tags=["global-runs"],
    operation_id="global_replay_run",
    summary="Replay a run with the same seed and events, optionally changing policy or capabilities",
    description=(
        "Creates a new run from the original's recipe: same seed and the same user events, "
        "re-injected at their cycles, with the given overrides. It plays as many cycles as the "
        "original (or `cycles`). An unchanged replay gives the same trace hash. Returns the new run "
        "summary with `replay_of` and `overrides`."
    ),
    responses=errors({404: "Unknown run_id.", 422: "Invalid override.", **TOO_MANY}),
    dependencies=RATE_LIMITED,
    openapi_extra=AGENT,
)
def replay_run(sim: Sim, run_id: RunId, body: ReplayIn) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key in ("policy", "uncertainty", "seed"):
        if getattr(body, key) is not None:
            overrides[key] = getattr(body, key)
    if body.adversary is not None:
        overrides["adversary"] = AdversaryConfig(**body.adversary.model_dump())
    if body.capabilities is not None:
        overrides["capabilities"] = tuple(sorted(body.capabilities.items()))
    return run_call(sim.runs.replay, run_id, overrides, body.cycles)


@router.get(
    "/sim/runs/{run_id}/snapshots",
    tags=["global-runs"],
    operation_id="global_get_run_snapshots",
    summary="Read the snapshots already computed from a cycle on",
    description=(
        "Returns the run summary and the cycle snapshots from index `start`. Use it to read a "
        "replay, which computes all its cycles at once. Read only."
    ),
    responses=ok(RunSnapshotsOut) | errors({404: "Unknown run_id.", 422: "`start` is not an integer."}),
    openapi_extra=AGENT,
)
def run_snapshots(
    sim: Sim,
    run_id: RunId,
    start: Annotated[int, Query(description="First cycle index to return (0-based)", examples=[0])] = 0,
) -> dict[str, Any]:
    return run_call(sim.runs.snapshots, run_id, start)


@router.get(
    "/sim/runs/{run_id}/trace",
    tags=["global-runs"],
    operation_id="global_get_run_trace",
    summary="Read a run's hash-chained audit log and replay recipe",
    description=(
        "Returns the audit log (each entry chained by hash), whether the chain `verified`, its "
        "`head` hash and the `recipe` (config and injected events) that rebuilds the run. Read only."
    ),
    responses=ok(RunTraceOut) | errors({404: "Unknown run_id.", 422: "Invalid path parameter."}),
    openapi_extra=AGENT,
)
def run_trace(sim: Sim, run_id: RunId) -> dict[str, Any]:
    return run_call(sim.runs.trace, run_id)


@router.get(
    "/sim/runs/{run_id}/report",
    tags=["global-runs"],
    operation_id="global_get_run_report",
    summary="Read a run's indicators, indices and consequence card",
    description=(
        "Returns the indicators, indices, the consequence card (level L0-L3, people affected, "
        "unserved MWh, cost) and the after-action keys. Works on running and finished runs. Read only."
    ),
    responses=ok(RunReportOut) | errors({404: "Unknown run_id.", 422: "Invalid path parameter."}),
    openapi_extra=AGENT,
)
def run_report(sim: Sim, run_id: RunId) -> dict[str, Any]:
    return run_call(sim.runs.report, run_id)


@router.post(
    "/sim/campaigns",
    status_code=201,
    tags=["experimentos"],
    summary="Campaña: matriz de corridas comparadas (modos I diagnóstico, II adversarial, III capacidades)",
    response_description="Tabla comparativa por política, índices de fragilidad decisional y de adaptación",
)
def create_campaign(sim: Sim, body: CampaignIn) -> dict[str, Any]:
    spec = CampaignSpec(
        mode=body.mode,
        templates=tuple(body.templates),
        policies=tuple(body.policies),
        seeds=tuple(body.seeds),
        uncertainty_levels=tuple(body.uncertainty_levels),
        adversary_variants=tuple(body.adversary_variants),
        capability_variants=tuple(
            (v.id, tuple(sorted(v.capabilities.items()))) for v in body.capability_variants
        ),
        horizon=body.horizon,
        objective=body.objective,
        budget=body.budget,
        random_seeds=body.random_seeds,
        point=body.point,
    )
    return run_call(sim.campaigns.run, spec)


@router.get("/sim/campaigns/{campaign_id}", tags=["experimentos"], summary="Resultado de una campaña")
def get_campaign(sim: Sim, campaign_id: str) -> dict[str, Any]:
    return run_call(sim.campaigns.get, campaign_id)


@router.get(
    "/sim/narrative",
    tags=["experimentos"],
    summary="Plantillas de narración en español para text_key, rationale_key y etiquetas",
)
def narrative() -> dict[str, Any]:
    return templates()


@router.get(
    "/sim/runs/{run_id}/after_action",
    tags=["global-runs"],
    operation_id="global_get_run_after_action",
    summary="Read a run's after-action review in Spanish",
    description=(
        "Returns the after-action review built from fixed Spanish templates (deterministic). With "
        "the server's LLM adapter enabled it adds a `narrative`. Read only."
    ),
    responses=ok(AfterActionOut) | errors({404: "Unknown run_id.", 422: "Invalid path parameter."}),
    openapi_extra=AGENT,
)
def run_after_action(sim: Sim, run_id: RunId) -> dict[str, Any]:
    return run_call(sim.runs.after_action, run_id)
