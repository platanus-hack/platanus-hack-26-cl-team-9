"""Where a run takes place: the mapa 3 network of the operating point's year and that point's
secure base case (`domain/cascade/scenario.py`). The application supplies a `TheaterWorld` that
reads `data/processed`; tests supply a `StaticWorld`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from cascadasen.domain.cascade.scenario import OperatingPoint
from cascadasen.domain.theater.areas import TheaterNetwork

DEFENSES_ID = "cen_25f_edac"  # the only defence set of the mapa 3 engine: EDAC steps of the CEN 25F report


class TheaterWorld(Protocol):
    def points(self) -> list[str]: ...

    def load(self, point_id: str) -> tuple[TheaterNetwork, OperatingPoint]: ...


@dataclass
class StaticWorld:
    network: TheaterNetwork
    by_id: dict[str, OperatingPoint] = field(default_factory=dict)

    def points(self) -> list[str]:
        return list(self.by_id)

    def load(self, point_id: str) -> tuple[TheaterNetwork, OperatingPoint]:
        return self.network, self.by_id[point_id]
