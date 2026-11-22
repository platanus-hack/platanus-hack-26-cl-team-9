"""Request and response models of the sessions API (docs/sessions-api.md). Bounds mirror the overlay validation
in domain/cascade/overlay.py; the overlay re-checks everything that depends on the network."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cascadasen.api.agent_openapi import AgentOut
from cascadasen.api.simulation_schemas import TheaterNetworkOut

Tech = Literal["hidro", "termica", "bioenergia", "geotermica", "solar", "eolica"]
LoadKind = Literal["datacenter", "consumo"]

_MW = {"gt": 0, "le": 3000}
_LAT = {"ge": -56, "le": -17}
_LON = {"ge": -76, "le": -66}
_BUS_MW_MAX = 20000  # coarse schema guard; the overlay checks base value + MAX_ELEMENT_MW


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(_Body):
    point: str | None = Field(
        None,
        description="Operating point the session pins for its whole life. Default nov2026-1300. "
        "Valid ids are listed by GET /api/v1/sim/catalog (operating_points).",
        examples=["nov2026-1300"],
    )
    label: str | None = Field(
        None, max_length=80, description="Free text shown to the people who join.", examples=["Equipo 9"]
    )


class BusIn(_Body):
    name: str = Field(
        max_length=80, description="Display name of the new bus.", examples=["SE Datacenter Norte"]
    )
    lat: float = Field(**_LAT, description="Latitude in degrees (continental Chile).", examples=[-33.45])
    lon: float = Field(**_LON, description="Longitude in degrees (continental Chile).", examples=[-70.66])
    kv: float = Field(
        gt=0, description="Voltage in kV; must be one of the base network's voltages.", examples=[220]
    )


class BusPatch(_Body):
    name: str | None = Field(None, max_length=80, description="New display name.", examples=["SE Renombrada"])
    kv: float | None = Field(None, gt=0, description="New voltage in kV (a base voltage).", examples=[500])
    lat: float | None = Field(None, **_LAT, description="New latitude in degrees.", examples=[-33.4])
    lon: float | None = Field(None, **_LON, description="New longitude in degrees.", examples=[-70.6])
    load_mw: float | None = Field(
        None,
        ge=0,
        le=_BUS_MW_MAX,
        description="Bus demand in MW (replaces the base value; at most the base value + 3000 MW).",
        examples=[150],
    )
    gen_mw: float | None = Field(
        None,
        ge=0,
        le=_BUS_MW_MAX,
        description="Bus generation in MW (replaces the base value; at most the base value + 3000 MW). "
        "The bus keeps this value: it takes no share of the redispatch.",
        examples=[300],
    )
    sync_mw: float | None = Field(
        None,
        ge=0,
        le=_BUS_MW_MAX,
        description="Synchronous part of gen_mw in MW (at most gen_mw).",
        examples=[200],
    )
    inertia_mws: float | None = Field(
        None,
        ge=0,
        le=10 * _BUS_MW_MAX,
        description="Inertia at the bus in MW·s (at most 10 s × sync_mw).",
        examples=[800],
    )
    in_service: bool | None = Field(
        None, description="false takes the bus out of service (its lines drop out).", examples=[False]
    )


class LineIn(_Body):
    a: str = Field(description="From bus id (B###), from GET /network nodes.", examples=["B010"])
    b: str = Field(description="To bus id (B###), different from a.", examples=["B188"])
    kv: float = Field(gt=0, description="Voltage in kV; a base network voltage.", examples=[220])
    capacity_mw: float = Field(gt=0, le=5000, description="Thermal capacity in MW.", examples=[500])
    x_pu: float | None = Field(
        None,
        gt=0,
        le=1.0,
        description="Reactance in p.u. (100 MVA base). Default: line length × typical x/km for kv.",
        examples=[0.02],
    )
    name: str | None = Field(None, max_length=80, description="Display name.", examples=["Línea nueva"])


class LinePatch(_Body):
    capacity_mw: float | None = Field(None, gt=0, le=5000, description="New capacity in MW.", examples=[800])
    x_pu: float | None = Field(None, gt=0, le=1.0, description="New reactance in p.u.", examples=[0.015])
    in_service: bool | None = Field(
        None, description="false takes the line out of the network (not a sandbox cut).", examples=[False]
    )


class LoadIn(_Body):
    bus: str = Field(description="Bus id (B###) the load connects to.", examples=["B010"])
    mw: float = Field(**_MW, description="Demand in MW (0 < mw ≤ 3000).", examples=[120])
    kind: LoadKind = Field(description="datacenter or consumo (other consumption).", examples=["datacenter"])
    name: str = Field(max_length=80, description="Display name.", examples=["Datacenter Quilicura"])


class LoadPatch(_Body):
    mw: float | None = Field(None, **_MW, description="New demand in MW.", examples=[200])
    kind: LoadKind | None = Field(None, description="datacenter or consumo.", examples=["consumo"])
    name: str | None = Field(None, max_length=80, description="New display name.", examples=["DC ampliado"])
    in_service: bool | None = Field(None, description="false disconnects the load.", examples=[False])


class GeneratorIn(_Body):
    bus: str = Field(description="Bus id (B###) the generator connects to.", examples=["B020"])
    mw: float = Field(**_MW, description="Dispatched generation in MW (0 < mw ≤ 3000).", examples=[250])
    tech: Tech = Field(
        description="Technology; hidro, termica, bioenergia and geotermica are synchronous.",
        examples=["solar"],
    )
    synchronous: bool | None = Field(
        None, description="Override whether the unit adds synchronous MW and inertia.", examples=[False]
    )
    inertia_h: float | None = Field(
        None, gt=0, le=10, description="Inertia constant H in s (default 4 s, an assumption).", examples=[4.0]
    )
    name: str | None = Field(
        None, max_length=80, description="Display name.", examples=["Parque solar nuevo"]
    )


class GeneratorPatch(_Body):
    mw: float | None = Field(None, **_MW, description="New generation in MW.", examples=[300])
    tech: Tech | None = Field(None, description="New technology.", examples=["eolica"])
    synchronous: bool | None = Field(None, description="Synchronous override.", examples=[True])
    inertia_h: float | None = Field(
        None, gt=0, le=10, description="New inertia constant H in s.", examples=[5.0]
    )
    name: str | None = Field(
        None, max_length=80, description="New display name.", examples=["Central renombrada"]
    )
    in_service: bool | None = Field(None, description="false disconnects the generator.", examples=[False])


class CutIn(_Body):
    lines: list[str] = Field(
        min_length=1,
        max_length=3,
        description="1 to 3 line ids (R### base or U### session) to open in the sandbox.",
        examples=[["R012"]],
    )


class RepairIn(_Body):
    lines: list[str] = Field(
        default_factory=list, max_length=200, description="Open line ids to close again.", examples=[["R012"]]
    )
    all: bool = Field(False, description="true closes every open line.", examples=[True])


class ActionIn(_Body):
    action: str = Field(
        description="Action id from GET /api/v1/sim/catalog (actions).", examples=["restore_element"]
    )
    target: str = Field(
        description="Area (A06) or corridor (A06-A07) id the action applies to.", examples=["A06-A07"]
    )
    role: str = Field(
        description="Proposing role; must be one of the action's proposers in the catalog.",
        examples=["operations"],
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters, if any.", examples=[{}]
    )
    agent: str | None = Field(
        None,
        max_length=64,
        description="Name of the external agent, recorded in the audit log.",
        examples=["bot-1"],
    )


# ------------------------------------------------------------------ responses (documentation only)
class SessionDocOut(AgentOut):
    """Session document."""

    session_id: str = Field(description="Session id; goes in the path of every session call.")
    label: str | None = Field(description="Optional label given on creation.")
    point: str = Field(description="Operating point the session is pinned to.")
    revision: int = Field(description="Bumped by every change, run activity included.")
    dataset_revision: int = Field(
        description="Bumped only by edits, reset, cut and repair; use it for If-Match."
    )
    overlay: dict[str, Any] = Field(description="The session's edits over the base dataset.")
    open_lines: list[str] = Field(description="Lines open in the sandbox cut.")
    runs: dict[str, dict[str, Any]] = Field(
        description="Run id -> created_at, dataset_revision, cycle, status."
    )
    created_at: str = Field(description="ISO 8601 creation time.")
    updated_at: str = Field(description="ISO 8601 time of the last change.")
    last_op: dict[str, Any] = Field(description="Last change: op, ids, by, revision, dataset_revision.")
    share_path: str = Field(description="Browser link path, /?sesion=<sid>.")
    expires_at: str = Field(description="ISO 8601 expiry, 24 h after the last change.")


class SessionWarningOut(AgentOut):
    """A warning about the edited network."""

    code: str = Field(description="isolated_bus, unbalanced_island or no_sync_to_redispatch.")
    ids: list[str] = Field(description="Buses the warning is about.")
    message: str = Field(description="Spanish message.")


class EditOut(AgentOut):
    """Result of an edit: element id, revisions, warnings and redispatch."""

    id: str | None = Field(None, description="Id of the element added, changed or deleted; absent on reset.")
    revision: int = Field(description="Session revision after the edit.")
    dataset_revision: int = Field(description="Dataset revision after the edit (also the ETag).")
    warnings: list[SessionWarningOut] = Field(description="Warnings about the edited network.")
    balance: list[dict[str, Any]] = Field(description="Redispatch per island (an assumption).")


class SessionNetworkOut(TheaterNetworkOut):
    """The session's edited 188-bus network."""

    session_id: str = Field(description="Session id.")
    revision: int = Field(description="Session revision.")
    dataset_revision: int = Field(description="Dataset revision (also the ETag); send it as If-Match.")
    out_of_service: dict[str, list[str]] = Field(description="Buses and lines out of service.")
    loads: list[dict[str, Any]] = Field(description="Loads and datacenters added by the session.")
    generators: list[dict[str, Any]] = Field(description="Generators added by the session.")
    warnings: list[SessionWarningOut] = Field(description="Warnings about the edited network.")
    balance: list[dict[str, Any]] = Field(description="Redispatch per island (an assumption).")
    baseline: dict[str, Any] = Field(description="Loading, overloads, islands and load shed with no cut.")


class CutStateOut(AgentOut):
    """Sandbox state: open lines and the cascade timeline."""

    revision: int = Field(description="Session revision.")
    dataset_revision: int = Field(description="Dataset revision (also the ETag).")
    open_lines: list[str] = Field(description="Lines open in the sandbox.")
    timeline: dict[str, Any] = Field(
        description="Cascade timeline with the open lines (the baseline when none)."
    )
    notice: str = Field(description="Every scenario is hypothetical and simulated.")
