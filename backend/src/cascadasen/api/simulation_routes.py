"""HTTP routes of the simulation API: reduced network, physical contingencies, strategic runs and
campaigns (docs/stack.md 7 and 7.1). Mounted by `create_app`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from cascadasen.api.simulation_schemas import (
    CampaignIn,
    EventIn,
    NetworkOut,
    ReplayIn,
    RunCreate,
    RunSummary,
    SimulateRequest,
    StepIn,
)
from cascadasen.application.run_campaign import CampaignNotFoundError, CampaignSpec
from cascadasen.application.run_experiment import RunNotFoundError, run_config
from cascadasen.application.simulate import SimulateCommand, SimulationInputError, SimulationTimeoutError
from cascadasen.application.simulation_service import SimulationService
from cascadasen.domain.theater.cycle import AdversaryConfig, RunFinishedError, RunInputError
from cascadasen.domain.theater.narrative import templates

router = APIRouter(prefix="/api/v1")


def get_simulation(request: Request) -> SimulationService:
    sim = request.app.state.simulation
    if sim is None:
        service = request.app.state.service
        if service is None:
            raise HTTPException(503, "No hay snapshot de la red. Ejecuta `cascadasen-build` primero.")
        sim = SimulationService.from_snapshot(service.s)
        request.app.state.simulation = sim
    return sim


Sim = Annotated[SimulationService, Depends(get_simulation)]


def input_error(exc: SimulationInputError) -> HTTPException:
    return HTTPException(422, exc.detail())


@router.get(
    "/sim/network",
    response_model=NetworkOut,
    tags=["simulación"],
    summary="Áreas y corredores de la red reducida: los objetivos seleccionables",
)
def network(sim: Sim) -> dict[str, Any]:
    return sim.network_view()


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
    except CampaignNotFoundError as exc:
        raise HTTPException(404, f"No existe la campaña: {exc.args[0]}") from exc


@router.get(
    "/sim/catalog", tags=["experimentos"], summary="Eventos, acciones, políticas, objetivos y plantillas"
)
def sim_catalog(sim: Sim) -> dict[str, Any]:
    return sim.catalog()


@router.post(
    "/sim/runs",
    response_model=RunSummary,
    status_code=201,
    tags=["experimentos"],
    summary="Crear una corrida del teatro de operaciones",
)
def create_run(sim: Sim, body: RunCreate) -> dict[str, Any]:
    data = body.model_dump(exclude={"auto_run"})
    data["initial_events"] = [e.model_dump() for e in body.initial_events]
    return run_call(lambda: sim.runs.create(run_config(data), body.auto_run))


@router.get(
    "/sim/runs/{run_id}", tags=["experimentos"], summary="Estado real, observado y estimado por agente"
)
def get_run(sim: Sim, run_id: str) -> dict[str, Any]:
    return run_call(sim.runs.state, run_id)


@router.post(
    "/sim/runs/{run_id}/events",
    tags=["experimentos"],
    summary="Seleccionar un nodo y disparar un evento (se aplica en el próximo ciclo)",
)
def inject_event(sim: Sim, run_id: str, body: EventIn) -> dict[str, Any]:
    return run_call(sim.runs.inject, run_id, body.type, body.target, body.params, body.cause)


@router.post("/sim/runs/{run_id}/step", tags=["experimentos"], summary="Avanzar n ciclos de 5 minutos")
def step_run(sim: Sim, run_id: str, body: StepIn) -> dict[str, Any]:
    return run_call(sim.runs.step, run_id, body.cycles)


@router.post(
    "/sim/runs/{run_id}/replay",
    response_model=RunSummary,
    status_code=201,
    tags=["experimentos"],
    summary="Repetir con la misma semilla y eventos, cambiando política o capacidades",
)
def replay_run(sim: Sim, run_id: str, body: ReplayIn) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key in ("policy", "uncertainty", "seed"):
        if getattr(body, key) is not None:
            overrides[key] = getattr(body, key)
    if body.adversary is not None:
        overrides["adversary"] = AdversaryConfig(**body.adversary.model_dump())
    if body.capabilities is not None:
        overrides["capabilities"] = tuple(sorted(body.capabilities.items()))
    return run_call(sim.runs.replay, run_id, overrides, body.cycles)


@router.get("/sim/runs/{run_id}/trace", tags=["experimentos"], summary="Log de auditoría encadenado y receta")
def run_trace(sim: Sim, run_id: str) -> dict[str, Any]:
    return run_call(sim.runs.trace, run_id)


@router.get("/sim/runs/{run_id}/report", tags=["experimentos"], summary="Indicadores, índices y consecuencia")
def run_report(sim: Sim, run_id: str) -> dict[str, Any]:
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
    tags=["experimentos"],
    summary="Informe posterior a la acción en español (determinista, desde plantillas)",
)
def run_after_action(sim: Sim, run_id: str) -> dict[str, Any]:
    return run_call(sim.runs.after_action, run_id)
