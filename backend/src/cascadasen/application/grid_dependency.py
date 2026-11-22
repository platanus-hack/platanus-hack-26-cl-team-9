"""Who feeds whom and how critical each substation is, on the grid as it stands after the user's changes (docs/dependency.md).

Why: the heat maps must describe the grid the user is looking at. With cuts or substations out, the flow changes and so
does who depends on whom: the changes are applied, their cascade settles, and the measures run on what is left.
Stateless; the last results are kept in memory because criticality runs one cascade per substation (0.2 to 1.9 s on
an M4, several times that on production). Dependencia alone (`criticality=False`) skips it and takes milliseconds.
`warm_workflow` fills the memory at API startup with the base case of every hour and the web's Desastres.
"""

from __future__ import annotations

import json

from cascadasen.application.cache import BoundedMap
from cascadasen.application.grid_simulation import prepare_edits
from cascadasen.domain.cascade.criticality import criticality_workflow
from cascadasen.domain.cascade.engine import run_cascade_state
from cascadasen.domain.cascade.network import bus_id
from cascadasen.domain.cascade.scenario import OperatingPoint
from cascadasen.domain.cascade.tracing import dependency_workflow
from cascadasen.domain.theater.world import TheaterWorld

CACHE_SIZE = 32  # (point, changes) results kept per process
# Warmed at API startup with the base case of every hour: the Desastres of web/src/cascade/Scenarios.tsx (Apagón 25F,
# Apagón 2011 Ancoa, Terremoto 2010 Charrúa) as (point, open_lines, out_buses). Keep in sync with that list.
DISASTERS: list[tuple[str, list[str], list[str]]] = [
    ("feb2025-1500", ["R239"], []),
    ("nov2026-2000", ["R006"], []),
    ("nov2026-2000", [], ["B043"]),
]


class GridDependency:
    def __init__(self, world: TheaterWorld) -> None:
        self.world = world
        # request threads and the startup warm-up share the cache
        self._cache: BoundedMap[tuple, dict] = BoundedMap(CACHE_SIZE)

    def dependency_workflow(
        self,
        point: str,
        open_lines: list[str],
        out_buses: list[str],
        changes: list[dict] | None = None,
        *,
        criticality: bool = True,
    ) -> dict:
        """`criticality=False` returns only who feeds whom (`gen_mw`, `people_fed`, `share_of_people`), the same
        values as the full answer, for the same substations."""
        key = (
            point,
            tuple(sorted(set(open_lines))),
            tuple(sorted(set(out_buses))),
            json.dumps(changes or [], sort_keys=True),
            criticality,
        )
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        out = self._compute(
            point, open_lines, out_buses, changes, criticality=criticality
        )  # not under the lock
        self._cache.put(key, out)
        return out

    def warm_workflow(self) -> None:
        """Compute the full answer (with criticality) for the base case of every hour and the Desastres, so those maps
        are instant even right after a deploy. Called once at API startup in a background thread."""
        for point, open_lines, out_buses in [(p, [], []) for p in self.world.points()] + DISASTERS:
            self.dependency_workflow(point, open_lines, out_buses)

    def _compute(
        self,
        point: str,
        open_lines: list[str],
        out_buses: list[str],
        changes: list[dict] | None,
        *,
        criticality: bool = True,
    ) -> dict:
        _, edited, kept, _ = prepare_edits(
            self.world, point, open_lines, out_buses, allow_empty=True, changes=changes
        )
        settled, still_open = _after_cascade(edited.net, edited.point, kept)
        fed = {
            r["bus"]: r
            for r in dependency_workflow(edited.net, settled.gen, settled.load, settled.people, still_open)
        }
        if criticality:
            rows = criticality_workflow(edited.net, settled, still_open)
        else:  # the substations criticality would score: those with a line still in service
            in_service = {b for ln in edited.net.lines if ln.id not in still_open for b in (ln.a, ln.b)}
            rows = {bus: {} for bus in sorted(in_service)}
        nodes = {}
        for bus, row in rows.items():
            key = bus_id(bus)
            extra = fed.get(key, {})
            nodes[key] = {
                **row,
                "gen_mw": round(float(settled.gen[bus]), 1),
                "people_fed": extra.get("people_fed", 0),
                "share_of_people": extra.get("share_of_people", 0.0),
            }
        return {
            "point": point,
            "open_lines": sorted(still_open),
            "out_buses": sorted(set(out_buses)),
            "nodes": nodes,
        }


def _after_cascade(net, point: OperatingPoint, cuts: list[str]) -> tuple[OperatingPoint, frozenset[str]]:
    """The point once the cascade of the user's cuts settled: what still runs, and every line that ended open."""
    if not cuts:
        return point, frozenset()
    _, state = run_cascade_state(net, point, cuts)
    settled = OperatingPoint(
        point.id, point.label, state.load, state.gen, state.sync, state.inertia, point.people
    )
    return settled, frozenset(state.open_lines)
