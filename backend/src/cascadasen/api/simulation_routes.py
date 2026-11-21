"""HTTP routes of the simulation API: reduced network, physical contingencies, strategic runs and
campaigns (docs/stack.md 7 and 7.1). Mounted by `create_app`."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from cascadasen.api.simulation_schemas import NetworkOut, SimulateRequest
from cascadasen.application.simulate import SimulateCommand, SimulationInputError, SimulationTimeoutError
from cascadasen.application.simulation_service import SimulationService

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
