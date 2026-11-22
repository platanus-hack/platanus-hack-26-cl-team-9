"""Request and response bodies of `POST /grids/stress` and `POST /grids/select` (docs/stress.md)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cascadasen.api.agent_openapi import AgentOut
from cascadasen.application.grid_stress import LINE_OUT_HINT, MAX_CHANGES, MAX_FACTOR

POINT = Field(description="Operating point id (feb2025-1500, feb2025-0300, nov2026-1300, nov2026-2000).")


class StressChange(BaseModel):
    """One change, applied to every element the filters pick. Filters combine (all must hold); none: the whole
    country. `factor` multiplies each element; `add` is one total for the filter, split by the current value."""

    model_config = ConfigDict(extra="forbid")

    target: Literal["population", "demand", "generation", "lines", "substation"] = Field(
        description="population (people; demand follows), demand (MW alone), generation (MW), lines (capacity), "
        "substation (a new substation next to the one that serves `places[0]`, with its own lines)."
    )
    buses: list[str] = Field(default=[], description="Substation ids B###.")
    zones: list[str] = Field(default=[], description="Zones NG, NC, CE, CS, SU.")
    areas: list[str] = Field(default=[], description="Operating areas A01-A13.")
    comunas: list[str] = Field(
        default=[], description="Comunas by CUT code or name (population and demand only)."
    )
    places: list[str] = Field(
        default=[],
        max_length=10,
        description="Places as a person names them, each resolved to ONE substation: a substation name (S/E "
        "ANTOFAGASTA), a comuna (the substation that serves most of its people), a province or region (its most "
        "populous comuna) or an area name. Use it to put a new load or plant at a point (`add`); the report says "
        "which substation each place became. For a whole comuna's population use `comunas`.",
        examples=[["Iquique"]],
    )
    tech: list[str] = Field(
        default=[],
        description="Generation only: hidro, solar, eolica, carbon, gas, diesel, bioenergia, geotermica, "
        "termica (carbon + gas + diesel), bateria (new capacity only). With `add` where the chosen substations "
        "have none of these technologies, a new plant of that technology is built there.",
    )
    lines: list[str] = Field(default=[], description="Lines only: line ids R###.")
    kv: list[float] = Field(default=[], description="Lines only: voltage levels (66, 110, 154, 220, 500).")
    factor: float | None = Field(
        default=None,
        ge=0.0,
        le=MAX_FACTOR,
        description="Multiplies the value (lines: capacity, more than 0; to take a line out of service put it in "
        "`open_lines`).",
    )
    add: float | None = Field(
        default=None, description="Adds this total (people for population, MW otherwise); negative lowers it."
    )
    x_factor: float | None = Field(
        default=None, gt=0.0, le=MAX_FACTOR, description="Lines only: multiplies the reactance x_pu."
    )
    name: str | None = Field(default=None, max_length=60, description="Substation only: its name.")
    lat: float | None = Field(
        default=None, description="Substation only: latitude (default: next to `places[0]`)."
    )
    lon: float | None = Field(
        default=None, description="Substation only: longitude (default: next to `places[0]`)."
    )
    load_mw: float | None = Field(default=None, gt=0.0, description="Substation only: demand it serves, MW.")
    generator_mw: float | None = Field(
        default=None,
        gt=0.0,
        description="Substation only: generation it injects, MW; `tech` has its technology.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> StressChange:
        own = (self.name, self.lat, self.lon, self.load_mw, self.generator_mw)
        if self.target == "substation":
            if len(self.places) != 1:
                raise ValueError("substation: indica un solo lugar en places")
            if self.buses or self.zones or self.areas or self.comunas or self.lines or self.kv:
                raise ValueError("substation: solo places, name, lat, lon, load_mw, generator_mw y tech")
            if self.factor is not None or self.add is not None or self.x_factor is not None:
                raise ValueError("substation: no lleva factor ni add")
            if self.generator_mw and len(self.tech) != 1:
                raise ValueError("substation: con generator_mw indica una tecnología en tech")
            return self
        if any(v is not None for v in own):
            raise ValueError(
                f"{self.target}: name, lat, lon, load_mw y generator_mw son solo para substation"
            )
        if self.target == "lines":
            if self.add is not None or (self.factor is None and self.x_factor is None):
                raise ValueError("lines: usa factor y/o x_factor")
            if self.factor is not None and self.factor <= 0:
                raise ValueError(LINE_OUT_HINT)
            if self.comunas or self.buses or self.tech or self.places:
                raise ValueError("lines: filtra por lines, kv, zones o areas")
            return self
        if (self.factor is None) == (self.add is None):
            raise ValueError(f"{self.target}: indica factor o add, no ambos")
        if self.x_factor is not None or self.lines or self.kv:
            raise ValueError(f"{self.target}: x_factor, lines y kv son solo para lines")
        if self.tech and self.target != "generation":
            raise ValueError("tech es solo para generation")
        if self.comunas and self.target == "generation":
            raise ValueError("generation: filtra por buses, zones, areas o tech")
        if self.comunas and (self.buses or self.zones or self.areas or self.places):
            raise ValueError("comunas no se combina con buses, zones, areas o places")
        return self


class PrepareIn(BaseModel):
    """Changes that prepare a scenario. Nothing runs and nothing is stored: send the same `changes` with
    /grids/simulate, /grids/dependency or /grids/cost to run a failure on the prepared grid."""

    model_config = ConfigDict(extra="forbid")

    point: str = POINT
    changes: list[StressChange] = Field(
        min_length=1, max_length=MAX_CHANGES, description="Changes, applied in order."
    )


class PrepareOut(BaseModel):
    """The prepared grid with no failure."""

    point: str = POINT
    changes: list[dict[str, Any]] = Field(description="Per change: matched count, deltas and the elements.")
    per_capita_w: float = Field(description="Demand per added person at this point, W (assumption).")
    totals: dict[str, Any] = Field(description="People, demand and generation of the prepared grid.")
    overloaded_lines: list[dict[str, Any]] = Field(
        description="Lines over the cascade's limit with no failure, by id: a simulation starts with them."
    )
    should_feed: dict[str, Any] = Field(
        description="Per generating substation (by id) and per zone: the people it should feed."
    )
    redispatch: list[dict[str, Any]] = Field(description="Generation the island's synchronous units moved.")
    health: dict[str, Any] | None = Field(
        None, description="Health index of the prepared grid before any failure (docs/health.md, no N-1)."
    )
    warnings: list[dict[str, Any]] = Field(
        description="Overlay warnings (isolated buses, no synchronous units)."
    )
    assumptions: list[dict[str, Any]] = Field(description="Assumptions behind the numbers.")


class PlaceOut(AgentOut):
    """The one substation a place resolves to (the same rule as `places` in a change)."""

    place: str = Field(description="The place as it was asked.")
    bus: str = Field(description="Substation id B### of the 188-bus network.")
    bus_name: str = Field(description="Substation name.")
    area: str = Field(description="Operating area A01-A13 of the substation.")
    area_name: str | None = Field(description="Name of that area.")
    how: str = Field(description="How the place was resolved, in Spanish (say it to the person).")


class LineMatch(BaseModel):
    """One line that matches the name."""

    id: str = Field(description="Line id R### (use it in `open_lines` or `lines`).")
    name: str = Field(description="Its two end substations and voltage, as the web names it.")
    kv: float = Field(description="Voltage level, kV.")
    a: str = Field(description="Substation id B### of one end.")
    b: str = Field(description="Substation id B### of the other end.")
    capacity_mw: float = Field(description="Thermal capacity of the reduced line, MW.")


class LineLookupOut(AgentOut):
    """The lines whose name matches the query, in id order (a lookup, never a ranking)."""

    query: str = Field(description="The line as it was asked.")
    how: str = Field(description="How the name was read, in Spanish (which substations).")
    matched: int = Field(description="Lines that match.")
    lines: list[LineMatch] = Field(description="At most 12 matching lines, in id order.")
    truncated: bool = Field(description="True when more than 12 lines matched: name both ends.")


class SimulateOut(BaseModel):
    """The cascade of the failures on the prepared grid."""

    point: str = POINT
    open_lines: list[str] = Field(description="Cuts that applied.")
    out_buses: list[str] = Field(description="Substations out of service.")
    dropped_lines: list[str] = Field(description="Lines that went with their substation.")
    direct: dict[str, Any] = Field(
        description="Load, generation and people the outages take away before the cascade."
    )
    warnings: list[dict[str, Any]] = Field(description="Overlay warnings.")
    timeline: dict[str, Any] = Field(description="Cascade timeline: events, frames, frequency and summary.")
    supply: dict[str, Any] = Field(
        description="Per generating substation (by id) and per zone: should_feed, feeds, pct_fed."
    )
