"""Entities of the unified grid. Pure data, no I/O.

Every entity carries the ids it has in each source and a list of provenance entries, so any
value shown in the UI can be traced back to the source record (or flagged as an assumption).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeKind(StrEnum):
    SUBSTATION = "substation"
    TAP = "tap"  # derivation point on a line ("TAP OFF")
    JUNCTION = "junction"  # structure or point where lines meet without a substation
    DANGLING = "dangling"  # line end with no identifiable substation


class EdgeKind(StrEnum):
    LINE = "line"
    COLOCATED = "colocated"  # assumed busbar coupling between adjacent substations


@dataclass(frozen=True)
class Provenance:
    source: str  # SourceInfo.id
    record: str | None = None  # id of the record in that source
    field: str | None = None  # attribute(s) taken from it
    method: str | None = None  # how it was matched or derived
    is_assumption: bool = False


@dataclass(frozen=True)
class SourceInfo:
    id: str
    name: str
    publisher: str
    url: str
    provides: tuple[str, ...]
    records: int = 0
    fetched_at: str | None = None
    notes: str = ""


# ---------- raw records as delivered by the source adapters (driven ports) ----------


@dataclass
class RawSubstation:
    source: str
    record_id: str
    name: str
    lon: float | None = None
    lat: float | None = None
    kv: float | None = None
    segment: str | None = None
    system: str | None = None
    owner: str | None = None
    region_code: str | None = None
    comuna_code: str | None = None
    cen_id: int | None = None  # Infotecnica id (IDE carries it as ID_SUBEST)
    cen_code: str | None = None  # Infotecnica nemotecnico (SE001G0010)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawBusbar:
    source: str
    record_id: str
    substation_cen_id: int
    name: str
    kv: float | None


@dataclass
class RawLine:
    """A line or line section with geometry (IDE) or with official end points (CEN tramo)."""

    source: str
    record_id: str
    name: str
    kv: float | None = None
    circuit: str | None = None
    segment: str | None = None
    system: str | None = None
    owner: str | None = None
    length_km: float | None = None
    coords: list[tuple[float, float]] | None = None
    end1: str | None = None  # raw end-point description (CEN tramo)
    end2: str | None = None
    line_code: str | None = None  # parent line nemotecnico
    status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawPlant:
    source: str
    record_id: str
    name: str
    tech: str | None = None
    mw: float | None = None
    lon: float | None = None
    lat: float | None = None
    status: str | None = None
    operating: bool = True
    system: str | None = None
    owner: str | None = None
    fuel: str | None = None
    region_code: str | None = None
    comuna_code: str | None = None
    comuna_name: str | None = None
    connection_bus: str | None = None  # model bus name when the source declares it
    inertia_s: float | None = None
    build_year: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawStorage:
    source: str
    record_id: str
    name: str
    lon: float | None = None
    lat: float | None = None
    mw: float | None = None
    hours: float | None = None
    equipment: str | None = None
    owner: str | None = None
    substation_name: str | None = None
    connection_bus: str | None = None
    build_year: int | None = None


@dataclass
class RawBus:
    """Bus of an electrical model (PyPSA-CL): one per substation and voltage level."""

    source: str
    name: str
    kv: float | None
    lon: float | None
    lat: float | None
    comuna_name: str | None = None
    region_name: str | None = None


@dataclass
class RawBranch:
    source: str
    name: str
    bus0: str
    bus1: str
    kv: float | None
    s_nom_mva: float | None
    r_ohm: float | None
    x_ohm: float | None
    r_pu: float | None
    x_pu: float | None
    build_year: int | None
    asset_type: str | None


@dataclass
class RawComuna:
    source: str
    cut: str
    name: str
    region_code: str
    region_name: str
    province_name: str | None
    population: int
    households: int | None
    dwellings: int | None
    centroid: tuple[float, float] | None
    geometry: dict[str, Any] | None  # GeoJSON geometry


@dataclass
class RawCensusZone:
    source: str
    zone_id: str
    cut: str
    population: int
    lon: float
    lat: float
    urban: bool


@dataclass
class SourceBundle:
    """Everything the adapters delivered for one build."""

    sources: list[SourceInfo] = field(default_factory=list)
    substations: list[RawSubstation] = field(default_factory=list)
    cen_substations: list[RawSubstation] = field(default_factory=list)
    busbars: list[RawBusbar] = field(default_factory=list)
    geo_lines: list[RawLine] = field(default_factory=list)
    cen_sections: list[RawLine] = field(default_factory=list)
    cen_lines: dict[str, dict[str, Any]] = field(default_factory=dict)
    plants: list[RawPlant] = field(default_factory=list)
    cen_plants: list[RawPlant] = field(default_factory=list)
    model_generators: list[RawPlant] = field(default_factory=list)
    storage: list[RawStorage] = field(default_factory=list)
    model_storage: list[RawStorage] = field(default_factory=list)
    buses: list[RawBus] = field(default_factory=list)
    branches: list[RawBranch] = field(default_factory=list)
    comunas: list[RawComuna] = field(default_factory=list)
    census_zones: list[RawCensusZone] = field(default_factory=list)


# ---------- unified entities ----------


@dataclass
class Node:
    id: str
    kind: NodeKind
    name: str
    lon: float | None
    lat: float | None
    kv: float | None = None
    kv_levels: list[float] = field(default_factory=list)
    segment: str | None = None
    system: str | None = None
    owner: str | None = None
    region_code: str | None = None
    comuna_code: str | None = None
    site: str | None = None
    location_source: str | None = None
    ids: dict[str, Any] = field(default_factory=dict)
    provenance: list[Provenance] = field(default_factory=list)
    # derived
    component: int = -1
    degree: int = 0
    macro_zone: str | None = None
    delivers: bool = False
    served_population: float = 0.0
    served_households: float = 0.0
    generation_mw: float = 0.0
    storage_mw: float = 0.0

    @property
    def located(self) -> bool:
        return self.lon is not None and self.lat is not None


@dataclass
class ElectricalParams:
    r_ohm: float | None
    x_ohm: float | None
    s_nom_mva: float | None
    source: str
    branch: str
    note: str = ""


@dataclass
class Edge:
    id: str
    kind: EdgeKind
    name: str
    source_node: str
    target_node: str
    kv: float | None = None
    circuit: str | None = None
    segment: str | None = None
    system: str | None = None
    owner: str | None = None
    length_km: float | None = None
    topology_source: str = ""
    geometry_source: str | None = None
    coords: list[tuple[float, float]] | None = None
    electrical: ElectricalParams | None = None
    ids: dict[str, Any] = field(default_factory=dict)
    provenance: list[Provenance] = field(default_factory=list)
    is_assumption: bool = False


@dataclass
class Plant:
    id: str
    name: str
    tech: str
    mw: float
    lon: float
    lat: float
    node: str | None
    connection_method: str
    connection_distance_km: float | None
    status: str | None
    operating: bool
    system: str | None
    owner: str | None
    fuel: str | None
    region_code: str | None
    comuna_code: str | None
    cen_id: int | None = None
    cen_name: str | None = None
    inertia_s: float | None = None
    model_units: list[str] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class Storage:
    id: str
    name: str
    lon: float | None
    lat: float | None
    node: str | None
    connection_method: str
    mw: float | None
    hours: float | None
    equipment: str | None
    owner: str | None
    build_year: int | None
    source: str
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class ServiceShare:
    node: str
    population: float
    households: float
    share: float  # fraction of the comuna's population


@dataclass
class Comuna:
    cut: str
    name: str
    region_code: str
    region_name: str
    province_name: str | None
    population: int
    households: int | None
    dwellings: int | None
    centroid: tuple[float, float] | None
    macro_zone: str | None
    served_by: list[ServiceShare] = field(default_factory=list)


@dataclass
class MacroZone:
    id: str
    name: str
    region_codes: list[str]
    color: tuple[int, int, int]
    population: int = 0
    substations: int = 0
    generation_mw: float = 0.0


@dataclass
class ModelBus:
    name: str
    kv: float | None
    lon: float | None
    lat: float | None
    node: str | None
    match_method: str | None


@dataclass
class ModelBranch:
    name: str
    bus0: str
    bus1: str
    node0: str | None
    node1: str | None
    kv: float | None
    s_nom_mva: float | None
    r_ohm: float | None
    x_ohm: float | None
    r_pu: float | None
    x_pu: float | None
    build_year: int | None
    asset_type: str | None
    edges: list[str] = field(default_factory=list)


@dataclass
class GridSnapshot:
    version: int
    built_at: str
    sources: list[SourceInfo]
    nodes: list[Node]
    edges: list[Edge]
    plants: list[Plant]
    storage: list[Storage]
    comunas: list[Comuna]
    macro_zones: list[MacroZone]
    model_buses: list[ModelBus]
    model_branches: list[ModelBranch]
    stats: dict[str, Any]
    assumptions: list[str]
    comuna_geometry: dict[str, dict[str, Any]] = field(default_factory=dict)
