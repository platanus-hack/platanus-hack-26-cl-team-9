"""HTTP routes of shared sessions (docs/sessions-api.md): session documents, edits of the 188-bus
network, the sandbox cut, runs nested in a session and a Server-Sent Events stream of revisions.
Agent-facing routes follow docs/openapi.md (x-sub50-agent marker, explicit operation ids,
English OpenAPI text, ErrorResponse). Error details stay in Spanish."""

# no `from __future__ import annotations`: the element routes are built in a factory and FastAPI
# must resolve their body models from the closure
import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cascadasen.api import agent_openapi
from cascadasen.api.agent_openapi import AGENT, ok
from cascadasen.api.limits import SseSlots, client_ip
from cascadasen.api.session_schemas import (
    ActionIn,
    BusIn,
    BusPatch,
    CutIn,
    CutStateOut,
    EditOut,
    GeneratorIn,
    GeneratorPatch,
    LineIn,
    LinePatch,
    LoadIn,
    LoadPatch,
    RepairIn,
    SessionCreate,
    SessionDocOut,
    SessionNetworkOut,
)
from cascadasen.api.simulation_routes import get_simulation, run_call
from cascadasen.api.simulation_schemas import (
    AfterActionOut,
    EventIn,
    ReplayIn,
    RunActionOut,
    RunCreate,
    RunEventOut,
    RunReportOut,
    RunSnapshotsOut,
    RunStateOut,
    RunStepOut,
    RunTraceOut,
    SessionRunOut,
    StepIn,
)
from cascadasen.application.sessions import (
    SESSION_ID,
    PreconditionFailedError,
    SessionLimitError,
    SessionNotFoundError,
    SessionService,
)
from cascadasen.domain.cascade.overlay import OverlayError
from cascadasen.domain.ports import ConflictError
from cascadasen.domain.theater.cycle import AdversaryConfig
from cascadasen.infrastructure.settings import Settings

router = APIRouter(prefix="/api/v1/sessions")

ERRORS = {
    404: "The session, run or element does not exist, or the id is malformed.",
    409: "Conflict: the element is still referenced, the run finished, another writer won, or the session is "
    "busy with another request for longer than the lock timeout (10 s by default) or has 5 waiting; retry "
    "after Retry-After.",
    412: "If-Match does not match the current dataset_revision; re-read the network and retry.",
    422: "Invalid input: detail names the field and, when useful, the valid values.",
    429: "Rate limit reached; wait the seconds in Retry-After.",
}


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return agent_openapi.errors({code: ERRORS[code] for code in codes})


WRITE_ERRORS = errors(404, 409, 412, 422, 429)
RUN_WRITE_ERRORS = errors(404, 409, 422, 429)
READ_ERRORS = errors(404, 409, 422)


def get_sessions(request: Request) -> SessionService:
    svc = request.app.state.sessions
    if svc is None:
        sim = get_simulation(request)
        settings: Settings = request.app.state.settings
        svc = SessionService(
            sim.world,
            sim.physics,
            sim.store,
            sim.run_cache,
            interpreter=sim.runs.interpreter,
            advisor=sim.runs.advisor,
            ttl_s=settings.session_ttl_hours * 3600,
            version=settings.version,
        )
        request.app.state.sessions = svc
    return svc


Sessions = Annotated[SessionService, Depends(get_sessions)]


def session_id(
    sid: Annotated[
        str,
        Path(
            description="Session id (22 URL-safe characters) returned by create_session or shared as "
            "?sesion=<sid> in the browser URL.",
            examples=["Q2xhdWRlU2Vzc2lvbklkMQ"],
        ),
    ],
) -> str:
    if not SESSION_ID.match(sid):
        raise HTTPException(404, f"No existe la sesión: {sid}")
    return sid


Sid = Annotated[str, Depends(session_id)]
RunId = Annotated[
    str,
    Path(
        description="Run id (12 hex characters) returned by create_run; GET /sessions/{sid} lists them "
        "under runs.",
        examples=["3f9a0c2b7d1e"],
    ),
]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description="Optional dataset_revision the edit is based on, as returned in the ETag of "
        'GET /network, /state or an edit ("3"). A different current dataset_revision gives 412; run '
        "activity does not change it.",
        examples=['"3"'],
    ),
]
Agent = Annotated[
    str,
    Header(
        alias="X-Sub50-Agent",
        max_length=64,
        description="Who makes the change (agent or user name); recorded in the session's last_op.",
        examples=["bot-1"],
    ),
]


def session_call(fn, *args, **kwargs) -> Any:
    try:
        return run_call(fn, *args, **kwargs)
    except SessionNotFoundError as exc:
        raise HTTPException(404, f"No existe la sesión: {exc.args[0]}") from exc
    except OverlayError as exc:
        raise HTTPException(404 if exc.not_found else 409 if exc.conflict else 422, exc.detail()) from exc
    except PreconditionFailedError as exc:
        raise HTTPException(412, "La sesión cambió (If-Match no coincide); relee y reintenta") from exc
    except ConflictError as exc:
        raise HTTPException(409, "La sesión cambió en otra instancia; reintenta") from exc
    except SessionLimitError as exc:
        raise HTTPException(422, str(exc)) from exc


def if_revision(value: str | None) -> int | None:
    if value is None or value.strip() == "*":
        return None
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise HTTPException(412, 'If-Match debe ser una revisión de la sesión, p. ej. "3"') from exc


def etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'"{revision}"'


def limit(request: Request, name: str, key: str) -> None:
    s: Settings = request.app.state.settings
    per, window = {
        "create": (s.rate_create_per_hour, 3600.0),
        "cut": (s.rate_cuts_per_minute, 60.0),
        "write": (s.rate_writes_per_minute, 60.0),
    }[name]
    request.app.state.limiter.check(name, key, per, window)


def serial(request: Request, sid: str):
    """Hold the session's lock: one request at a time per session in this process (409 when busy)."""
    return request.app.state.session_locks.hold(sid)


# ------------------------------------------------------------------ session documents
@router.post(
    "",
    status_code=201,
    tags=["sessions"],
    operation_id="create_session",
    summary="Create a shared session",
    description="Creates a session: an editable copy of the 188-bus network pinned to one operating "
    "point (default nov2026-1300). Call it first; every other session call takes the returned "
    "session_id in the path. The session expires 24 h after its last change. Anyone with the id can "
    "read and edit it (share_path is the browser link). Rate limited per client IP.",
    responses=ok(SessionDocOut, 201) | errors(422, 429),
    openapi_extra=AGENT,
)
def create_session(
    request: Request,
    response: Response,
    svc: Sessions,
    body: SessionCreate | None = None,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "create", client_ip(request))
    body = body or SessionCreate()
    doc = session_call(svc.create, body.point, body.label, agent)
    etag(response, doc["revision"])
    return doc


@router.get(
    "/{sid}",
    tags=["sessions"],
    operation_id="get_session",
    summary="Read a session document",
    description="Returns the session document: point, revision (bumped by every change, runs "
    "included), dataset_revision (bumped only by edits, reset, cut and repair), overlay (the edits), "
    "open_lines "
    "(sandbox cut), runs (id -> created_at, dataset_revision, cycle, status), last_op, share_path and "
    "expires_at. The ETag header is the revision; send it as If-None-Match to get 304 when nothing "
    "changed (polling fallback when SSE is not available). No side effects.",
    responses=ok(SessionDocOut)
    | {
        304: {"description": "Not modified: If-None-Match equals the current revision."},
        **READ_ERRORS,
    },
    openapi_extra=AGENT,
)
def get_session(
    request: Request,
    sid: Sid,
    response: Response,
    svc: Sessions,
    if_none_match: Annotated[
        str | None,
        Header(alias="If-None-Match", description='Last ETag seen, e.g. "3".', examples=['"3"']),
    ] = None,
) -> Any:
    with serial(request, sid):
        doc = session_call(svc.get, sid)
    tag = f'"{doc["revision"]}"'
    if if_none_match and tag in {t.strip().removeprefix("W/") for t in if_none_match.split(",")}:
        return Response(status_code=304, headers={"ETag": tag})
    etag(response, doc["revision"])
    return doc


@router.delete(
    "/{sid}",
    status_code=204,
    tags=["sessions"],
    operation_id="delete_session",
    summary="Delete a session and its runs",
    description="Deletes the session document and the records of its runs. Every client of the "
    "session loses it (their SSE stream ends). Irreversible.",
    responses=errors(404, 409, 422, 429),
    openapi_extra=AGENT,
)
def delete_session(request: Request, sid: Sid, svc: Sessions) -> Response:
    limit(request, "write", sid)
    with serial(request, sid):
        session_call(svc.delete, sid)
    return Response(status_code=204)


@router.post(
    "/{sid}/reset",
    tags=["sessions"],
    operation_id="reset_session",
    summary="Drop every network edit of a session",
    description="Replaces the overlay with an empty one, so the network is the base dataset again. "
    "Runs keep the dataset they were created with; the sandbox cut keeps the lines that still exist. "
    "Bumps revision and dataset_revision; the ETag is the dataset_revision.",
    responses=ok(EditOut) | WRITE_ERRORS,
    openapi_extra=AGENT,
)
def reset_session(
    request: Request,
    response: Response,
    sid: Sid,
    svc: Sessions,
    if_match: IfMatch = None,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "write", sid)
    with serial(request, sid):
        out = session_call(svc.reset, sid, agent, if_revision(if_match))
    etag(response, out["dataset_revision"])
    return out


# ------------------------------------------------------------------ network and element CRUD
@router.get(
    "/{sid}/network",
    tags=["session-network"],
    operation_id="get_session_network",
    summary="Read the session's 188-bus network",
    description="Returns the edited network: nodes and lines (origin base|session, is_assumption, "
    "overridden), buses with load and generation, loads[] and generators[] added by the session, "
    "areas, corridors, out_of_service, warnings, balance (the redispatch assumption) and baseline "
    "(loading and load shed with no cut). With no edits it is the base dataset. Use it to get bus "
    "(B###) and line (R###, U###) ids before editing or cutting. The ETag is the dataset_revision, "
    "to send as If-Match on edits.",
    responses=ok(SessionNetworkOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_session_network(request: Request, sid: Sid, response: Response, svc: Sessions) -> dict[str, Any]:
    with serial(request, sid):
        view = session_call(svc.network_view, sid)
    etag(response, view["dataset_revision"])
    return view


def _element_routes(
    kind: str,
    plural: str,
    noun: str,
    create_model: type[BaseModel],
    patch_model: type[BaseModel],
    example_id: str,
    create_text: str,
    patch_text: str,
) -> None:
    ElementId = Annotated[
        str,
        Path(description=f"Id of the {noun}, from GET /sessions/{{sid}}/network.", examples=[example_id]),
    ]
    edit = (
        " Bumps revision and dataset_revision (the ETag). Returns {id, revision, dataset_revision, "
        "warnings, balance}; the island of the edit is "
        "rebalanced by redispatching base synchronous units (an assumption)."
    )

    @router.post(
        f"/{{sid}}/{plural}",
        status_code=201,
        tags=["session-network"],
        operation_id=f"add_{kind}",
        summary=f"Add a {noun} to the session network",
        description=create_text + edit,
        responses=ok(EditOut, 201) | WRITE_ERRORS,
        openapi_extra=AGENT,
    )
    def add(
        request: Request,
        response: Response,
        sid: Sid,
        svc: Sessions,
        body: create_model,  # type: ignore[valid-type]
        if_match: IfMatch = None,
        agent: Agent = "anon",
    ) -> dict[str, Any]:
        limit(request, "write", sid)
        fields = body.model_dump(exclude_unset=True)
        with serial(request, sid):
            out = session_call(svc.add, sid, kind, fields, agent, if_revision(if_match))
        etag(response, out["dataset_revision"])
        return out

    @router.patch(
        f"/{{sid}}/{plural}/{{element_id}}",
        tags=["session-network"],
        operation_id=f"update_{kind}",
        summary=f"Change a {noun}",
        description=patch_text + " Only the fields sent change; null clears a session value." + edit,
        responses=ok(EditOut) | WRITE_ERRORS,
        openapi_extra=AGENT,
    )
    def update(
        request: Request,
        response: Response,
        sid: Sid,
        element_id: ElementId,
        svc: Sessions,
        body: patch_model,  # type: ignore[valid-type]
        if_match: IfMatch = None,
        agent: Agent = "anon",
    ) -> dict[str, Any]:
        limit(request, "write", sid)
        fields = body.model_dump(exclude_unset=True)
        with serial(request, sid):
            out = session_call(svc.patch, sid, kind, element_id, fields, agent, if_revision(if_match))
        etag(response, out["dataset_revision"])
        return out

    @router.delete(
        f"/{{sid}}/{plural}/{{element_id}}",
        tags=["session-network"],
        operation_id=f"delete_{kind}",
        summary=f"Delete a session {noun}",
        description=f"Deletes a {noun} the session added. Base elements are never deleted (409): "
        "PATCH them with in_service=false instead." + edit,
        responses=ok(EditOut) | WRITE_ERRORS,
        openapi_extra=AGENT,
    )
    def delete(
        request: Request,
        response: Response,
        sid: Sid,
        element_id: ElementId,
        svc: Sessions,
        if_match: IfMatch = None,
        agent: Agent = "anon",
    ) -> dict[str, Any]:
        limit(request, "write", sid)
        with serial(request, sid):
            out = session_call(svc.remove, sid, kind, element_id, agent, if_revision(if_match))
        etag(response, out["dataset_revision"])
        return out


_element_routes(
    "bus",
    "buses",
    "bus",
    BusIn,
    BusPatch,
    "B188",
    "Adds a substation bus (B### after the base buses) at lat/lon with a base voltage. Connect it "
    "with add_line; a bus with no line gives an isolated_bus warning.",
    "Changes a base bus (stored as an override) or a session bus: name, kv, position, load, "
    "generation, synchronous MW, inertia or in_service.",
)
_element_routes(
    "line",
    "lines",
    "line",
    LineIn,
    LinePatch,
    "U001",
    "Adds a transmission line (U###) between two in-service buses with a base voltage. x_pu "
    "defaults from the length and voltage.",
    "Changes capacity_mw, x_pu or in_service of a base line (R###) or a session line (U###).",
)
_element_routes(
    "load",
    "loads",
    "load or datacenter",
    LoadIn,
    LoadPatch,
    "D001",
    "Adds a demand (D###) on a bus: kind datacenter or consumo. Pick the bus from the network, for "
    "example the nearest 220 kV or higher substation.",
    "Changes mw, kind, name or in_service of a session load (D###).",
)
_element_routes(
    "generator",
    "generators",
    "generator",
    GeneratorIn,
    GeneratorPatch,
    "G001",
    "Adds a generator (G###) on a bus. hidro, termica, bioenergia and geotermica units are synchronous "
    "and add inertia (H default 4 s, an assumption).",
    "Changes mw, tech, synchronous, inertia_h, name or in_service of a session generator (G###).",
)


# ------------------------------------------------------------------ sandbox
SANDBOX = (
    " Re-runs the cascade from the base case with every open line and returns {revision, "
    "dataset_revision, open_lines, timeline, notice}; all clients of the session see the same cut. "
    "Bumps revision and dataset_revision (the ETag)."
)


@router.post(
    "/{sid}/cut",
    tags=["session-sandbox"],
    operation_id="cut_lines",
    summary="Open 1 to 3 lines in the session sandbox",
    description="Adds 1 to 3 line ids (R### or U###, from get_session_network) to the open lines. "
    "This shows the physical consequence of losing those lines; it does not search for the worst cut."
    + SANDBOX,
    responses=ok(CutStateOut) | WRITE_ERRORS,
    openapi_extra=AGENT,
)
def cut_lines(
    request: Request,
    response: Response,
    sid: Sid,
    svc: Sessions,
    body: CutIn,
    if_match: IfMatch = None,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "cut", sid)
    with serial(request, sid):
        out = session_call(svc.cut, sid, body.lines, agent, if_revision(if_match))
    etag(response, out["dataset_revision"])
    return out


@router.post(
    "/{sid}/repair",
    tags=["session-sandbox"],
    operation_id="repair_lines",
    summary="Close open lines in the session sandbox",
    description="Closes the given open lines, or all of them with all=true." + SANDBOX,
    responses=ok(CutStateOut) | WRITE_ERRORS,
    openapi_extra=AGENT,
)
def repair_lines(
    request: Request,
    response: Response,
    sid: Sid,
    svc: Sessions,
    body: RepairIn,
    if_match: IfMatch = None,
    agent: Agent = "anon",
) -> dict[str, Any]:
    if not body.all and not body.lines:
        raise HTTPException(422, {"field": "lines", "message": "Indica las líneas o all=true."})
    limit(request, "cut", sid)
    with serial(request, sid):
        out = session_call(svc.repair, sid, body.lines, body.all, agent, if_revision(if_match))
    etag(response, out["dataset_revision"])
    return out


@router.get(
    "/{sid}/state",
    tags=["session-sandbox"],
    operation_id="get_cut_state",
    summary="Read the session sandbox state",
    description="Returns {revision, dataset_revision, open_lines, timeline, notice}: the cascade "
    "timeline with the current open lines (the baseline when none). The ETag is the dataset_revision. "
    "No side effects.",
    responses=ok(CutStateOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_cut_state(request: Request, sid: Sid, response: Response, svc: Sessions) -> dict[str, Any]:
    with serial(request, sid):
        out = session_call(svc.state, sid)
    etag(response, out["dataset_revision"])
    return out


# ------------------------------------------------------------------ live revisions (SSE)
def _event(rev: dict[str, Any], retry_ms: int | None = None) -> str:
    head = f"retry: {retry_ms}\n" if retry_ms else ""
    data = json.dumps({"type": "revision", **rev}, ensure_ascii=False)
    return f"{head}id: {rev['revision']}\nevent: revision\ndata: {data}\n\n"


async def _revisions(
    svc: SessionService, sid: str, current: dict[str, Any], s: Settings, slots: SseSlots, key: Any
) -> AsyncIterator[str]:
    start = last_head = last_ping = time.monotonic()
    try:
        yield _event(current, retry_ms=2000)
        while time.monotonic() - start < s.sse_max_s:
            await asyncio.sleep(s.sse_poll_s)
            now = time.monotonic()
            try:
                if now - last_head >= s.sse_head_s:  # another instance may have written it
                    await run_in_threadpool(svc.head, sid)
                    last_head = now
                rev = await run_in_threadpool(svc.revision, sid)
            except SessionNotFoundError:
                return
            if rev["revision"] != current["revision"]:
                current = rev
                yield _event(rev)
            if now - last_ping >= s.sse_heartbeat_s:
                last_ping = now
                yield ": ping\n\n"
    finally:
        slots.release(key)


@router.get(
    "/{sid}/events",
    tags=["sessions"],
    summary="Stream session revisions (Server-Sent Events)",
    description="text/event-stream: on connect and after every change, `event: revision` with data "
    "{type, revision, dataset_revision, op, ids, by}; `: ping` comments as heartbeat. The server closes the stream "
    "after about a minute and EventSource reconnects. Not an agent tool: see docs/sessions-api.md.",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Revision events."},
        **errors(404, 429),
    },
)
async def session_events(request: Request, sid: Sid, svc: Sessions) -> StreamingResponse:
    s: Settings = request.app.state.settings
    current = await run_in_threadpool(session_call, svc.revision, sid)
    slots: SseSlots = request.app.state.sse_slots
    key = (sid, client_ip(request))
    if not slots.acquire(key, s.sse_per_session_ip):
        raise HTTPException(
            429, "Demasiadas conexiones en vivo a esta sesión desde tu IP.", headers={"Retry-After": "5"}
        )
    return StreamingResponse(
        _revisions(svc, sid, current, s, slots, key),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ session runs
RUN_TEXT = " The run must belong to the session (GET /sessions/{sid} lists runs)."


def _run_etag(response: Response, out: dict[str, Any]) -> dict[str, Any]:
    if "session_revision" in out:
        etag(response, out["session_revision"])
    return out


@router.post(
    "/{sid}/runs",
    status_code=201,
    tags=["session-runs"],
    operation_id="create_run",
    summary="Create a strategic run on the session network",
    description="Creates a run of the strategic theatre on the session's current network and point. "
    "The run keeps that dataset even if the session is edited later. point/operating_point must be "
    "empty or equal to the session point. Templates, policies and events come from "
    "GET /api/v1/sim/catalog. At most 20 runs per session. Returns the run summary and "
    "session_revision.",
    responses=ok(SessionRunOut, 201) | RUN_WRITE_ERRORS,
    openapi_extra=AGENT,
)
def create_run(
    request: Request, response: Response, sid: Sid, svc: Sessions, body: RunCreate, agent: Agent = "anon"
) -> dict[str, Any]:
    limit(request, "write", sid)
    data = body.model_dump(exclude={"auto_run"})
    data["initial_events"] = [e.model_dump() for e in body.initial_events]
    with serial(request, sid):
        return _run_etag(response, session_call(svc.create_run, sid, data, body.auto_run, agent))


@router.get(
    "/{sid}/runs/{rid}",
    tags=["session-runs"],
    operation_id="get_run",
    summary="Read a session run",
    description="Returns {run, latest, resources, series}: the run summary (cycle, status, rebuilt, "
    "trace_matches), the latest snapshot (real, observed and estimated state, decisions, executed), "
    "resources and the metric series." + RUN_TEXT,
    responses=ok(RunStateOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_run(request: Request, sid: Sid, rid: RunId, svc: Sessions) -> dict[str, Any]:
    with serial(request, sid):
        return session_call(svc.run_command, sid, rid, "state")


@router.post(
    "/{sid}/runs/{rid}/events",
    tags=["session-runs"],
    operation_id="inject_run_event",
    summary="Inject an event into a session run",
    description="Queues an event (type from the catalog events) on a target area, corridor or bus; it "
    "applies on the next cycle. Returns the resolved target and the run summary." + RUN_TEXT,
    responses=ok(RunEventOut) | RUN_WRITE_ERRORS,
    openapi_extra=AGENT,
)
def inject_run_event(
    request: Request,
    response: Response,
    sid: Sid,
    rid: RunId,
    svc: Sessions,
    body: EventIn,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "write", sid)
    with serial(request, sid):
        out = session_call(
            svc.run_command, sid, rid, "inject", body.type, body.target, body.params, body.cause, by=agent
        )
    return _run_etag(response, out)


@router.post(
    "/{sid}/runs/{rid}/step",
    tags=["session-runs"],
    operation_id="step_run",
    summary="Advance a session run",
    description="Runs 1 to 72 cycles of 5 minutes and returns their snapshots. A finished run gives 409."
    + RUN_TEXT,
    responses=ok(RunStepOut) | RUN_WRITE_ERRORS,
    openapi_extra=AGENT,
)
def step_run(
    request: Request,
    response: Response,
    sid: Sid,
    rid: RunId,
    svc: Sessions,
    body: StepIn,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "write", sid)
    with serial(request, sid):
        return _run_etag(response, session_call(svc.run_command, sid, rid, "step", body.cycles, by=agent))


@router.post(
    "/{sid}/runs/{rid}/actions",
    tags=["session-runs"],
    operation_id="submit_run_action",
    summary="Submit an external agent's action to a session run",
    description="Queues a course of action (action id from the catalog, a target area or corridor, a "
    "role among the action's proposers) for the next cycle. It runs through the same validation, "
    "resource and crew checks as the commander's own actions and is recorded in the audit log. It is "
    "not capped by the commander's operator attention and skips its choice, conflict rules and "
    "vetoes. Returns "
    "{accepted, applies_at_cycle, action, target, role, notice}." + RUN_TEXT,
    responses=ok(RunActionOut) | RUN_WRITE_ERRORS,
    openapi_extra=AGENT,
)
def submit_run_action(
    request: Request,
    response: Response,
    sid: Sid,
    rid: RunId,
    svc: Sessions,
    body: ActionIn,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "write", sid)
    with serial(request, sid):
        out = session_call(
            svc.run_command,
            sid,
            rid,
            "action",
            body.action,
            body.target,
            body.role,
            body.params,
            body.agent or agent,
            by=agent,
        )
    return _run_etag(response, out)


@router.post(
    "/{sid}/runs/{rid}/replay",
    status_code=201,
    tags=["session-runs"],
    operation_id="replay_run",
    summary="Replay a session run with changes",
    description="Creates a new run in the session with the original seed, events and actions and the "
    "given overrides (policy, uncertainty, seed, adversary, capabilities), on the original run's "
    "dataset. Returns the new run summary with replay_of." + RUN_TEXT,
    responses=ok(SessionRunOut, 201) | RUN_WRITE_ERRORS,
    openapi_extra=AGENT,
)
def replay_run(
    request: Request,
    response: Response,
    sid: Sid,
    rid: RunId,
    svc: Sessions,
    body: ReplayIn,
    agent: Agent = "anon",
) -> dict[str, Any]:
    limit(request, "write", sid)
    overrides: dict[str, Any] = {}
    for key in ("policy", "uncertainty", "seed"):
        if getattr(body, key) is not None:
            overrides[key] = getattr(body, key)
    if body.adversary is not None:
        overrides["adversary"] = AdversaryConfig(**body.adversary.model_dump())
    if body.capabilities is not None:
        overrides["capabilities"] = tuple(sorted(body.capabilities.items()))
    with serial(request, sid):
        out = session_call(svc.run_command, sid, rid, "replay", overrides, body.cycles, by=agent)
    return _run_etag(response, out)


@router.get(
    "/{sid}/runs/{rid}/snapshots",
    tags=["session-runs"],
    operation_id="get_run_snapshots",
    summary="Read the snapshots of a session run",
    description="Returns {run, snapshots} with the snapshots already computed from cycle start." + RUN_TEXT,
    responses=ok(RunSnapshotsOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_run_snapshots(
    request: Request,
    sid: Sid,
    rid: RunId,
    svc: Sessions,
    start: Annotated[int, Query(ge=0, description="First cycle to return.", examples=[0])] = 0,
) -> dict[str, Any]:
    with serial(request, sid):
        return session_call(svc.run_command, sid, rid, "snapshots", start)


@router.get(
    "/{sid}/runs/{rid}/trace",
    tags=["session-runs"],
    operation_id="get_run_trace",
    summary="Read the audit log of a session run",
    description="Returns the hash-chained audit log, its head, verified and the recipe (config, "
    "injected events, actions) that rebuilds the run." + RUN_TEXT,
    responses=ok(RunTraceOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_run_trace(request: Request, sid: Sid, rid: RunId, svc: Sessions) -> dict[str, Any]:
    with serial(request, sid):
        return session_call(svc.run_command, sid, rid, "trace")


@router.get(
    "/{sid}/runs/{rid}/report",
    tags=["session-runs"],
    operation_id="get_run_report",
    summary="Read the report of a session run",
    description="Returns indicators, indices and the physical consequence of the run so far." + RUN_TEXT,
    responses=ok(RunReportOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_run_report(request: Request, sid: Sid, rid: RunId, svc: Sessions) -> dict[str, Any]:
    with serial(request, sid):
        return session_call(svc.run_command, sid, rid, "report")


@router.get(
    "/{sid}/runs/{rid}/after_action",
    tags=["session-runs"],
    operation_id="get_run_after_action",
    summary="Read the after-action report of a session run",
    description="Returns the deterministic after-action report in Spanish, built from templates." + RUN_TEXT,
    responses=ok(AfterActionOut) | READ_ERRORS,
    openapi_extra=AGENT,
)
def get_run_after_action(request: Request, sid: Sid, rid: RunId, svc: Sessions) -> dict[str, Any]:
    with serial(request, sid):
        return session_call(svc.run_command, sid, rid, "after_action")
