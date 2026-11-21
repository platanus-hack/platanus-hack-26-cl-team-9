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
