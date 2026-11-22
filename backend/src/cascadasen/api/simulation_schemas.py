"""Request and response models of the simulation API (docs/stack.md 7 and 7.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cascadasen.api.agent_openapi import AgentOut


class AreaOut(BaseModel):
    id: str = Field(description="Área de operación A01-A13 (docs/strategy.md 2.1)")
    name: str
    zone: str = Field(description="Macrozona: NG, NC, CE, CS, SU")
    lon: float | None
    lat: float | None
    population: float
    demand_mw: float = Field(description="Demanda en el punto de operación de referencia")
    generation_mw: float
    installed_mw: dict[str, float]
    storage_mw: float
    main_node: str | None = Field(description="Subestación troncal del área (objetivo por defecto)")
    anchors: list[str]
    aggregates: list[str] = Field(description="Ids reales de nodos (SE…) que agrupa el área")


class CorridorOut(BaseModel):
    id: str = Field(description="'A06-A07/500': áreas y clase de tensión")
    a: str
    b: str
    kv_class: str
    x_pu: float
    capacity_mw: float
    lines: int
    members: list[str] = Field(description="Ids reales de líneas (L…, T…) del corredor")
    is_assumption: bool
    source: str


class NetworkOut(BaseModel):
    version: int
    reference_operating_point: str
    zones: list[str]
    areas: list[AreaOut]
    corridors: list[CorridorOut]
    provenance: list[dict[str, Any]]


class GroupOut(BaseModel):
    zone: str = Field(description="NG, NC, CE, CS, SU")
    tech: str = Field(description="solar, eolica, hidro, termica, bioenergia, geotermica")
    share: float = Field(ge=0, le=1)


class SimulateRequest(BaseModel):
    scenario: str = Field("25F", description="Punto de operación: 25F, midday_2026, low_demand_2026")
    defenses: str = Field("25F", description="25F, implemented_dec2025, design_2026")
    behavior: str = Field("per_code", description="per_code | as_happened (solo con 25F)")
    elements_out: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="1 a 3 ids: corredor (A06-A07/500), área (A06), subestación real (SE…) o línea real (L…, T…)",
    )
    battery_mw: dict[str, float] = Field(default_factory=dict, description="MW por área o zona, 0 a 5000")
    group_out: list[GroupOut] = Field(
        default_factory=list, description="Pérdida común por zona y tecnología (C2)"
    )
    defenses_disabled: list[str] = Field(default_factory=list, description="pdce_zn, edac, edac:<zona>…")
    outage_duration_h: float | None = Field(None, description="0 a 2160 h; por defecto 4 h (supuesto)")
    cause: Literal["failure", "cyber_effect"] = "failure"
    frames: bool = Field(True, description="Incluir cuadros de animación (~10 Hz)")


class AdversaryIn(BaseModel):
    enabled: bool = Field(True, description="Whether the adversary plays", examples=[True])
    objective: str = Field(
        "reduce_observability",
        description="Adversary objective; see `GET /api/v1/sim/catalog` → `objectives`",
        examples=["reduce_observability"],
    )
    budget: float = Field(
        8, description="Adversary actions, 0 to 50 (digital action = 1, physical = 2)", examples=[8]
    )
    adaptive: bool = Field(
        True,
        description="True: it learns during the run (EXP3); False: it plays the template's plan",
        examples=[True],
    )


class EventIn(BaseModel):
    type: str = Field(
        description="Event type; see `GET /api/v1/sim/catalog` → `events`",
        examples=["C3_transmission_opening", "D1_telemetry_loss"],
    )
    target: str = Field(
        description=(
            "Area (A06), zone (NG), corridor (A06-A07/500), bus B###, line R###, defence function "
            "(pdce_zn) or real substation id (SE…)"
        ),
        examples=["A06", "B042"],
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides of the event's default size (catalog `events[].defaults`)",
        examples=[{}],
    )
    cause: Literal["intentional", "failure"] = Field(
        "intentional", description="Intentional event or plain failure", examples=["intentional"]
    )
    cycle: int | None = Field(
        None, ge=0, description="Only in `initial_events`: cycle at which it happens", examples=[0]
    )


class RunCreate(BaseModel):
    template: str = Field(
        "open_field",
        description="Experiment template; see `GET /api/v1/sim/catalog` → `templates`",
        examples=["flagship_observability", "open_field"],
    )
    policy: str = Field(
        "C",
        description="Defensive policy: A reactive, B preventive, C adaptive coordination",
        examples=["C"],
    )
    seed: int | None = Field(
        None,
        ge=0,
        description="Random seed; omitted means a fresh one, returned in the summary",
        examples=[11],
    )
    uncertainty: float = Field(
        1.0, description="0 perfect information, 1 baseline, 2 degraded", examples=[1.0]
    )
    horizon: int | None = Field(
        None, description="Cycles of 5 min (1 to 72); default is the template's", examples=[30]
    )
    adversary: AdversaryIn | None = Field(None, description="Default is the template's adversary")
    capabilities: dict[str, float] = Field(
        default_factory=dict,
        description="Capacity per defensive resource (mode III), 0 to 10000; see catalog `resources`",
        examples=[{"field_crews": 12}],
    )
    point: str | None = Field(
        None,
        description="Mapa 3 operating point (catalog `operating_points`); default is the template's",
        examples=["nov2026-1300"],
    )
    operating_point: str | None = Field(None, description="Alias of `point`", examples=["nov2026-1300"])
    initial_events: list[EventIn] = Field(
        default_factory=list,
        description="Events applied at their `cycle` (default 0)",
        examples=[[{"type": "C3_transmission_opening", "target": "A06", "cycle": 2}]],
    )
    auto_run: bool = Field(False, description="Play the run to the end before returning", examples=[False])
    llm_commander: bool = Field(
        False,
        description="C2 picks among validated actions with the server's LLM (rules if none is configured)",
        examples=[False],
    )
    stochastic: bool = Field(
        True,
        description="Chance in the world: event sizes, unplanned events, action and defence failures",
        examples=[True],
    )


class StepIn(BaseModel):
    cycles: int = Field(1, ge=1, le=72, description="Cycles of 5 minutes to advance", examples=[3])


class ReplayIn(BaseModel):
    policy: str | None = Field(None, description="New policy A, B or C", examples=["A"])
    uncertainty: float | None = Field(None, description="New uncertainty level, 0 to 2", examples=[2.0])
    seed: int | None = Field(None, description="New seed; omitted keeps the original", examples=[12])
    adversary: AdversaryIn | None = Field(None, description="New adversary; omitted keeps the original")
    capabilities: dict[str, float] | None = Field(
        None, description="New capacity per defensive resource", examples=[{"field_crews": 12}]
    )
    cycles: int | None = Field(
        None, ge=1, le=72, description="Cycles to play; default is what the original played", examples=[6]
    )


class RunSummary(BaseModel):
    run_id: str
    status: str
    cycle: int
    horizon: int
    t_min: int
    template: str
    policy: str
    seed: int
    uncertainty: float
    operating_point: str
    defenses: str
    adversary: dict[str, Any]
    rebuilt: bool = Field(False, description="La corrida se reconstruyó desde su registro persistido")
    trace_matches: bool | None = Field(
        None, description="Tras reconstruirla, si el hash del log coincide con el registrado"
    )
    notice: str
    replay_of: str | None = None
    overrides: dict[str, Any] | None = None


class SessionRunOut(RunSummary):
    """Run summary of a session run, with the session revision."""

    model_config = ConfigDict(extra="allow")
    session_revision: int = Field(description="Session revision after the command (also the ETag).")


class TheaterNetworkOut(AgentOut):
    """The 188-bus network: buses, lines, areas and corridors."""

    point: str = Field(description="Operating point of the network, e.g. nov2026-1300.")
    points: list[str] = Field(description="Operating points available.")
    nodes: list[dict[str, Any]] = Field(description="Buses B### with id, name, kv, lat, lon, area, zone.")
    lines: list[dict[str, Any]] = Field(
        description="Lines R### with id, a, b, kv, capacity_mw, x_pu, corridor."
    )
    buses: dict[str, dict[str, Any]] = Field(description="Load and generation per bus id at the point.")
    areas: list[dict[str, Any]] = Field(description="Operating areas with their buses and population.")
    corridors: list[dict[str, Any]] = Field(description="Corridors between areas with their lines.")
    defenses: dict[str, Any] = Field(description="Defence functions (EDAC, PDCE) by id.")
    zones: list[str] = Field(description="Macrozones, e.g. NG, NC, CE, CS, SU.")


class CatalogOut(AgentOut):
    """What an agent can choose from when creating and playing a run."""

    notice: str = Field(description="Every scenario is hypothetical and simulated.")
    events: list[dict[str, Any]] = Field(description="Event types with family, defaults and targets.")
    actions: list[dict[str, Any]] = Field(description="Courses of action with proposers, target and costs.")
    policies: list[dict[str, Any]] = Field(description="Defensive policies A, B and C.")
    objectives: list[str] = Field(description="Adversary objectives.")
    missions: list[dict[str, Any]] = Field(description="Missions with their continuity threshold.")
    templates: list[dict[str, Any]] = Field(description="Experiment templates.")
    operating_points: list[str] = Field(description="Operating points a run can use.")
    defense_sets: list[str] = Field(description="Defence sets.")
    zones: list[str] = Field(description="Macrozones.")
    resources: dict[str, Any] = Field(description="Defensive resources and their default capacity.")
    uncertainty_levels: dict[str, Any] = Field(description="Uncertainty levels 0, 1 and 2.")
    cycle_minutes: int = Field(description="Minutes per cycle.")
    llm: dict[str, Any] = Field(description="Whether the server's LLM commander is available, and its model.")


class RunStateOut(AgentOut):
    """Run summary, latest snapshot, resources and metric series."""

    run: RunSummary = Field(description="Run summary.")
    latest: dict[str, Any] | None = Field(description="Latest snapshot; null before the first step.")
    resources: dict[str, Any] = Field(description="Defensive resources left.")
    series: list[dict[str, Any]] = Field(description="Metrics of every cycle played.")


class RunEventOut(AgentOut):
    """The queued event: resolved target, area and the run summary."""

    run: RunSummary = Field(description="Run summary after the command.")
    accepted: bool = Field(description="Whether the event was queued.")
    applies_at_cycle: int = Field(description="Cycle at which the event applies.")
    resolved_target: str = Field(description="Target after resolving areas, buses or substation ids.")
    area: str | None = Field(description="Area of the target, when it has one.")
    notice: str | None = Field(description="Notice for intentional events; null for plain failures.")
    session_revision: int | None = Field(
        None, description="Session revision after the command; only on session runs."
    )


class RunStepOut(AgentOut):
    """The snapshots of the cycles played and the run summary."""

    run: RunSummary = Field(description="Run summary after the command.")
    snapshots: list[dict[str, Any]] = Field(description="One snapshot per cycle played.")
    session_revision: int | None = Field(
        None, description="Session revision after the command; only on session runs."
    )


class RunActionOut(AgentOut):
    """The queued external action and the run summary."""

    run: RunSummary = Field(description="Run summary after the command.")
    accepted: bool = Field(description="Whether the action was queued.")
    applies_at_cycle: int = Field(description="Cycle at which the action applies.")
    action: str = Field(description="Action id from the catalog.")
    target: str = Field(description="Target area or corridor.")
    role: str = Field(description="Role that proposes the action.")
    notice: str = Field(description="Every scenario is hypothetical and simulated.")
    session_revision: int | None = Field(
        None, description="Session revision after the command; only on session runs."
    )


class RunSnapshotsOut(AgentOut):
    """The snapshots already computed from a cycle, and the run summary."""

    run: RunSummary = Field(description="Run summary.")
    snapshots: list[dict[str, Any]] = Field(description="Snapshots from cycle `start`.")


class RunTraceOut(AgentOut):
    """Hash-chained audit log of a run and the recipe that rebuilds it."""

    head: str = Field(description="Hash of the last log entry.")
    verified: bool = Field(description="Whether the hash chain verifies.")
    entries: list[dict[str, Any]] = Field(description="Log entries in order.")
    recipe: dict[str, Any] = Field(description="Config, injected events and actions that rebuild the run.")


class RunReportOut(AgentOut):
    """Indicators, coordination and physical consequence of a run so far."""

    run_id: str = Field(description="Run id.")
    run: dict[str, Any] = Field(
        description="Template, policy, seed, uncertainty, horizon, cycles_run, finished, operating point."
    )
    notice: str = Field(description="Every scenario is hypothetical and simulated.")
    mission: dict[str, Any] = Field(description="Mission of the template and its continuity threshold.")
    indicators: dict[str, Any] = Field(description="Experimental indicators and indices.")
    coordination: dict[str, Any] = Field(description="Conflicts, contradictions and decision delays.")
    consequence: dict[str, Any] = Field(description="Unserved energy, people without power, worst level.")
    adversary: dict[str, Any] | None = Field(
        description="Adversary objective, budget and spend; null if none."
    )
    after_action: list[dict[str, Any]] = Field(description="Key moments by cycle.")
    incident: dict[str, Any] | None = Field(
        None,
        description="Only for runs started from a documented incident: sources, notes, mitigations and "
        "the consequence card (level, people, MW shed, MWh and cost over an assumed duration).",
    )
    trace_head: str = Field(description="Hash of the last audit log entry.")


class AfterActionOut(AgentOut):
    """Deterministic after-action report in Spanish."""

    run_id: str = Field(description="Run id.")
    question: str = Field(description="Question the template asks.")
    notice: str = Field(description="Every scenario is hypothetical and simulated.")
    policy: str = Field(description="Policy played.")
    summary: list[str] = Field(description="Summary sentences.")
    moments: list[Any] = Field(description="Key moments.")
    adversary: Any = Field(description="What the adversary did; null if none.")
    timeline: list[Any] = Field(description="Timeline of the run.")
    experimental: bool = Field(description="Always true: the indicators are experimental.")


class CapabilityVariant(BaseModel):
    id: str = Field(description="Nombre de la variante, p. ej. 'baseline', 'mas_cuadrillas'")
    capabilities: dict[str, float] = Field(default_factory=dict, description="Capacidad por recurso")


class CampaignIn(BaseModel):
    mode: Literal["diagnostic", "adversarial", "capability"] = "adversarial"
    templates: list[str] = Field(
        default_factory=lambda: ["flagship_observability"], min_length=1, max_length=6
    )
    policies: list[str] = Field(default_factory=lambda: ["A", "B", "C"], min_length=1, max_length=3)
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3], min_length=1, max_length=10)
    uncertainty_levels: list[float] = Field(default_factory=lambda: [1.0], min_length=1, max_length=3)
    adversary_variants: list[str] = Field(default_factory=lambda: ["static", "adaptive"])
    capability_variants: list[CapabilityVariant] = Field(
        default_factory=list, description="Modo III: la primera variante es la línea base"
    )
    horizon: int | None = Field(None, ge=1, le=72)
    objective: str | None = None
    budget: float | None = Field(None, ge=0, le=50)
    point: str | None = Field(None, description="Punto de operación del mapa 3 para todas las corridas")
    random_seeds: int | None = Field(
        None,
        ge=1,
        le=10,
        description="Sortear n semillas nuevas (se devuelven en spec.seeds) en vez de `seeds`",
    )
