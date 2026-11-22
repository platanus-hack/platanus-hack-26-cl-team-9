"""Documented-incident scenarios (docs/attack-sim.md): a bounded catalog and a launcher that creates a
strategic run from one of them inside a session. Everything after the launch (step, report,
after_action, replay) uses the existing run routes. No route ranks, sweeps or searches targets and
none accepts free-form effects: only ids of the catalog (cyber.md 8)."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from cascadasen.api.agent_openapi import AGENT, AgentOut, ok
from cascadasen.api.session_routes import (
    RUN_WRITE_ERRORS,
    Agent,
    Sessions,
    Sid,
    _run_etag,
    limit,
    serial,
    session_call,
)
from cascadasen.api.simulation_schemas import AdversaryIn, SessionRunOut
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.incident import incident_catalog

router = APIRouter(prefix="/api/v1")


class IncidentCatalogOut(AgentOut):
    """Documented incidents that can be replayed as simulated runs."""

    notices: list[str] = Field(description="Notices every result carries: hypothetical, not a prediction.")
    default_duration_h: dict[str, Any] = Field(description="Default outage hours, with is_assumption true.")
    incidents: list[dict[str, Any]] = Field(
        description="id, title, date, kind (cyber_documented or reference_not_cyber), verified, sources, "
        "notes, mitigations, operating_point (the session point the incident needs) and the effects the "
        "scenario applies (cycle, event type, target, params)."
    )


class IncidentRunIn(BaseModel):
    scenario: str = Field(
        description="Incident id from `GET /api/v1/attacks/catalog`.", examples=["huatacondo-2026"]
    )
    policy: str = Field("C", description="Defensive policy: A reactive, B preventive, C adaptive.")
    seed: int | None = Field(None, ge=0, description="Random seed; omitted means a fresh one.")
    duration_h: float | None = Field(
        None,
        gt=0,
        le=720,
        description="Outage hours that scale unserved energy and cost in the incident card. Always an "
        "assumption; omitted uses the catalog default.",
    )
    uncertainty: float = Field(1.0, description="0 perfect information, 1 baseline, 2 degraded.")
    stochastic: bool = Field(
        False,
        description="False (default): the incident is the script, with its catalog sizes and no unplanned "
        "events, so the consequence card is the incident's own. True adds the theatre's chance (unplanned "
        "external events, defences that may not act), which then also counts in the card.",
    )
    adversary: AdversaryIn | None = Field(
        None, description="Optional seeded abstract adversary. Off by default: the incident is the script."
    )


@router.get(
    "/attacks/catalog",
    tags=["incidents"],
    operation_id="get_attack_catalog",
    summary="List the documented incidents that can be replayed",
    description="Returns the bounded, curated catalog: each entry is a public incident with its linked "
    "sources, whether it is verified, and the effects (event type, area or zone, cycle) the scenario "
    "applies. Only effects are modelled, never techniques, and nobody is attributed. The list is not "
    "ranked. Read only.",
    responses=ok(IncidentCatalogOut),
    openapi_extra=AGENT,
)
def attack_catalog() -> dict[str, Any]:
    return incident_catalog(theater_config())


@router.post(
    "/sessions/{sid}/attacks/runs",
    status_code=201,
    tags=["incidents"],
    operation_id="start_incident_run",
    summary="Start a run from a documented incident",
    description="Creates a strategic run in the session from one catalog incident, with the defensive "
    "agents and the chosen policy. The adversary is off unless asked. Step it with `step_run`, read "
    "`get_run_report` (its `incident` block has the consequence card and mitigations) and "
    "`get_run_after_action`. Only catalog ids are accepted (422 otherwise). The incident runs at its own "
    "`operating_point` (see the catalog): the session must have been created at that point, or the "
    "call answers 422 with the point in `valid`. Scenario: the effect is "
    "modelled, not the attack; the consequence is simulated on a reduced network, not a prediction.",
    responses=ok(SessionRunOut, 201) | RUN_WRITE_ERRORS,
    openapi_extra=AGENT,
)
def start_incident_run(
    request: Request,
    response: Response,
    sid: Sid,
    svc: Sessions,
    body: IncidentRunIn,
    agent: Agent = "anon",
) -> dict[str, Any]:
    cfg = theater_config()
    if body.scenario not in cfg.incidents:
        raise HTTPException(
            422,
            {"field": "scenario", "message": "incidente desconocido", "valid": list(cfg.incidents)},
        )
    point = cfg.templates[body.scenario].operating_point
    limit(request, "write", sid)
    data = {
        "template": body.scenario,
        "policy": body.policy,
        "seed": body.seed,
        "duration_h": body.duration_h,
        "uncertainty": body.uncertainty,
        "stochastic": body.stochastic,
        "adversary": body.adversary.model_dump() if body.adversary else None,
    }
    with serial(request, sid):
        doc = session_call(svc.get, sid)
        if doc["point"] != point:
            raise HTTPException(
                422,
                {
                    "field": "scenario",
                    "message": f"el incidente corre a las {point}; crea una sesión con ese punto",
                    "valid": [point],
                },
            )
        out = session_call(svc.create_run, sid, data, False, agent)
    return _run_etag(response, out)
