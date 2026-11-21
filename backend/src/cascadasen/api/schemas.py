"""Response and request models of the HTTP API (OpenAPI at /docs)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NodeSummary(BaseModel):
    id: str
    kind: str = Field(description="substation | tap | junction | dangling")
    name: str
    kv: float | None
    kv_levels: list[float]
    segment: str | None = Field(description="NACIONAL, ZONAL, DEDICADO (segmento de transmisión)")
    system: str | None = Field(description="SEN, SEA (Aysén), SEM (Magallanes)…")
    owner: str | None
    region_code: str | None
    comuna_code: str | None
    macro_zone: str | None
    lon: float | None
    lat: float | None
    location_source: str | None
    component: int
    in_main_grid: bool
    degree: int
    delivers: bool = Field(description="subestación de entrega a distribución (abastece comunas)")
    served_population: int
    served_households: int
    generation_mw: float
    storage_mw: float
    site: str | None


class EdgeSummary(BaseModel):
    id: str
    kind: str = Field(description="line | colocated")
    name: str
    source: str
    target: str
    source_name: str
    target_name: str
    kv: float | None
    circuit: str | None
    segment: str | None
    system: str | None
    owner: str | None
    length_km: float | None
    topology_source: str
    geometry_source: str | None
    cen_tramos: int = Field(description="tramos oficiales del CEN asociados a esta línea")
    s_nom_mva: float | None = Field(description="capacidad del corredor (PyPSA-CL)")
    x_ohm: float | None
    r_ohm: float | None
    corridor_edges: int | None = Field(description="líneas que comparten el valor de corredor del modelo")
    model_branch: str | None
    is_assumption: bool


class NodePage(BaseModel):
    total: int
    items: list[NodeSummary]


class EdgePage(BaseModel):
    total: int
    items: list[EdgeSummary]


class Page(BaseModel):
    total: int
    items: list[dict[str, Any]]


class IslandsRequest(BaseModel):
    remove: list[str] = Field(min_length=1, max_length=20, description="ids de líneas (L…, T…) o nodos (SE…)")


class Island(BaseModel):
    id: int
    nodes: int
    substations: int
    generation_mw: float
    served_population: int
    macro_zones: list[str]
    state: str
    node_ids: list[str]
    sample: list[str]


class IslandsResponse(BaseModel):
    removed: list[str]
    islands: list[Island]
    new_islands: int
    population_without_supply: int
    note: str


class Health(BaseModel):
    status: str
    snapshot_built_at: str | None
    nodes: int
    edges: int
