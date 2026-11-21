"""Defence sets: under-frequency load shedding (EDAC), extreme-contingency shedding, the north
defence scheme (PDCE-ZN) and over-frequency curtailment (docs/stack.md 4.3-4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cascadasen.domain.simulation.params import Provenance, collect_provenance, load_params, value


class UnknownDefenseSetError(KeyError):
    pass


@dataclass(frozen=True)
class DefenseSet:
    id: str
    label_key: str
    edac_steps: tuple[tuple[float, float], ...]
    edac_delay_s: float
    extreme_threshold_hz: float
    extreme_gradients: tuple[float, ...]
    extreme_mw_by_zone: dict[str, float]
    pdce_active: bool
    pdce_t_sep_s: float
    pdce_north: str
    pdce_south: str
    pdce_limit_ns_mw: float
    pdce_limit_sn_mw: float
    weak_link_trip_s: float
    lfsm_start_hz: float
    lfsm_share_per_hz: float
    lfsm_tau_s: float
    provenance: tuple[Provenance, ...] = ()

    @classmethod
    def load(cls, set_id: str) -> DefenseSet:
        sets = load_params("defenses")["sets"]
        if set_id not in sets:
            raise UnknownDefenseSetError(set_id)
        s = sets[set_id]
        ext, pdce, lfsm = value(s["extreme_edac"]), value(s["pdce_zn"]), value(s["lfsm_o"])
        return cls(
            id=set_id,
            label_key=s["label_key"],
            edac_steps=tuple((float(hz), float(sh)) for hz, sh in value(s["edac_steps"])),
            edac_delay_s=float(value(s["edac_delay_s"])),
            extreme_threshold_hz=float(ext["threshold_hz"]),
            extreme_gradients=tuple(float(g) for g in ext["gradients_hz_s"]),
            extreme_mw_by_zone={k: float(v) for k, v in ext["mw_by_zone"].items()},
            pdce_active=bool(pdce["active"]),
            pdce_t_sep_s=float(pdce["t_sep_s"]),
            pdce_north=pdce["north"],
            pdce_south=pdce["south"],
            pdce_limit_ns_mw=float(pdce["limit_ns_mw"]),
            pdce_limit_sn_mw=float(pdce["limit_sn_mw"]),
            weak_link_trip_s=float(value(s["weak_link_trip_s"])),
            lfsm_start_hz=float(lfsm["start_hz"]),
            lfsm_share_per_hz=float(lfsm["share_per_hz"]),
            lfsm_tau_s=float(lfsm["time_constant_s"]),
            provenance=tuple(collect_provenance(s, f"defenses.{set_id}")),
        )

    def zone_edac_enabled(self, zone: str, disabled: set[str]) -> bool:
        return "edac" not in disabled and f"edac:{zone}" not in disabled

    def pdce_enabled(self, disabled: set[str]) -> bool:
        return self.pdce_active and "pdce_zn" not in disabled

    def defense_ids(self, zones: list[str]) -> list[str]:
        """Ids a scenario may disable (cyber.md C4)."""
        return ["pdce_zn", "edac", "extreme_edac", "lfsm_o", *(f"edac:{z}" for z in zones)]


def defense_sets() -> dict[str, dict[str, Any]]:
    return load_params("defenses")["sets"]


def documented_trips_25f() -> tuple[list[dict[str, Any]], list[Provenance]]:
    node = load_params("defenses")["as_happened_25F"]["documented_trips"]
    return list(value(node)), collect_provenance(node, "defenses.as_happened_25F.documented_trips")
