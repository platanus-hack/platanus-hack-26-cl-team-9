"""Request and response models of the simulation API (docs/stack.md 7 and 7.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    enabled: bool = True
    objective: str = Field("reduce_observability", description="Ver /sim/catalog → objectives")
    budget: float = Field(8, description="Acciones del adversario (digital = 1, física = 2)")
    adaptive: bool = Field(True, description="True: aprende (EXP3); False: juega el plan de la plantilla")


class EventIn(BaseModel):
    type: str = Field(
        description="Ver /sim/catalog → events, p. ej. D1_telemetry_loss, C3_transmission_opening"
    )
    target: str = Field(
        description="Área (A06), corredor (A06-A07/500), zona (NG), defensa (pdce_zn) o id real (SE…)"
    )
    params: dict[str, Any] = Field(default_factory=dict)
    cause: Literal["intentional", "failure"] = "intentional"
    cycle: int | None = Field(None, ge=0, description="Solo en initial_events: ciclo en que ocurre")


class RunCreate(BaseModel):
    template: str = Field("open_field", description="Ver /sim/catalog → templates (flagship_observability…)")
    policy: str = Field("C", description="A reactiva, B preventiva, C coordinación adaptativa")
    seed: int | None = Field(
        None, ge=0, description="Vacío: semilla al azar (cada corrida distinta), devuelta en la respuesta"
    )
    uncertainty: float = Field(1.0, description="0 información perfecta, 1 línea base, 2 degradado")
    horizon: int | None = Field(None, description="Ciclos de 5 min; por defecto el de la plantilla")
    adversary: AdversaryIn | None = Field(None, description="Por defecto el de la plantilla")
    capabilities: dict[str, float] = Field(
        default_factory=dict, description="Capacidad por recurso (modo III)"
    )
    point: str | None = Field(
        None,
        description="Punto de operación del mapa 3 (nov2026-1300, feb2025-1500…); por defecto el de la plantilla",
    )
    operating_point: str | None = Field(None, description="Alias de `point`")
    initial_events: list[EventIn] = Field(default_factory=list)
    auto_run: bool = Field(False, description="Correr hasta el final al crear")
    llm_commander: bool = Field(
        False, description="C2 elige entre acciones validadas con el LLM configurado (si no hay, usa reglas)"
    )
    stochastic: bool = Field(
        True,
        description="Azar del mundo: tamaño de eventos, eventos imprevistos, fallas de acciones y defensas",
    )


class StepIn(BaseModel):
    cycles: int = Field(1, ge=1, le=72)


class ReplayIn(BaseModel):
    policy: str | None = None
    uncertainty: float | None = None
    seed: int | None = None
    adversary: AdversaryIn | None = None
    capabilities: dict[str, float] | None = None
    cycles: int | None = Field(None, ge=1, le=72, description="Por defecto los ciclos que corrió la original")


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
    notice: str
    replay_of: str | None = None
    overrides: dict[str, Any] | None = None


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
