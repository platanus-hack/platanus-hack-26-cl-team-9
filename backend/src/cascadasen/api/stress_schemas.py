"""Request and response bodies of `POST /grids/stress` and `POST /grids/select` (docs/stress.md)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cascadasen.application.grid_stress import MAX_CHANGES, MAX_FACTOR

POINT = Field(description="Operating point id (feb2025-1500, feb2025-0300, nov2026-1300, nov2026-2000).")


class StressChange(BaseModel):
    """One change, applied to every element the filters pick. Filters combine (all must hold); none: the whole
    country. `factor` multiplies each element; `add` is one total for the filter, split by the current value."""

    model_config = ConfigDict(extra="forbid")

    target: Literal["population", "demand", "generation", "lines"] = Field(
        description="population (people; demand follows), demand (MW alone), generation (MW), lines (capacity)."
    )
    buses: list[str] = Field(default=[], description="Substation ids B###.")
    zones: list[str] = Field(default=[], description="Zones NG, NC, CE, CS, SU.")
    areas: list[str] = Field(default=[], description="Operating areas A01-A13.")
    comunas: list[str] = Field(
        default=[], description="Comunas by CUT code or name (population and demand only)."
    )
    tech: list[str] = Field(
        default=[],
        description="Generation only: hidro, solar, eolica, carbon, gas, diesel, bioenergia, geotermica, "
        "termica (carbon + gas + diesel).",
    )
    lines: list[str] = Field(default=[], description="Lines only: line ids R###.")
    kv: list[float] = Field(default=[], description="Lines only: voltage levels (66, 110, 154, 220, 500).")
    factor: float | None = Field(
        default=None, ge=0.0, le=MAX_FACTOR, description="Multiplies the value (lines: capacity)."
    )
    add: float | None = Field(
        default=None, description="Adds this total (people for population, MW otherwise); negative lowers it."
    )
    x_factor: float | None = Field(
        default=None, gt=0.0, le=MAX_FACTOR, description="Lines only: multiplies the reactance x_pu."
    )

    @model_validator(mode="after")
    def _consistent(self) -> StressChange:
        if self.target == "lines":
            if self.add is not None or (self.factor is None and self.x_factor is None):
                raise ValueError("lines: usa factor y/o x_factor")
            if self.comunas or self.buses or self.tech:
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
        if self.comunas and (self.buses or self.zones or self.areas):
            raise ValueError("comunas no se combina con buses, zones o areas")
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
    warnings: list[dict[str, Any]] = Field(
        description="Overlay warnings (isolated buses, no synchronous units)."
    )
    assumptions: list[dict[str, Any]] = Field(description="Assumptions behind the numbers.")


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
