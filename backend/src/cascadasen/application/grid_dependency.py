"""Who feeds whom and how critical each substation is, on the grid as it stands after the user's changes (docs/dependency.md).

Why: the heat maps must describe the grid the user is looking at. With cuts or substations out, the flow changes and so
does who depends on whom: the changes are applied, their cascade settles, and the measures run on what is left.
Stateless; the last results are kept in memory because criticality runs one cascade per substation (about 2 s).
"""

from __future__ import annotations

import json
from collections import OrderedDict

from cascadasen.application.grid_simulation import prepare_edits
from cascadasen.domain.cascade.criticality import criticality_workflow
from cascadasen.domain.cascade.engine import run_cascade_state
from cascadasen.domain.cascade.scenario import OperatingPoint
from cascadasen.domain.cascade.tracing import dependency_workflow
from cascadasen.domain.theater.world import TheaterWorld

CACHE_SIZE = 32  # (point, changes) results kept per process


class GridDependency:
    def __init__(self, world: TheaterWorld) -> None:
        self.world = world
        self._cache: OrderedDict[tuple, dict] = OrderedDict()

    def dependency_workflow(
        self, point: str, open_lines: list[str], out_buses: list[str], changes: list[dict] | None = None
    ) -> dict:
        key = (
            point,
            tuple(sorted(set(open_lines))),
            tuple(sorted(set(out_buses))),
            json.dumps(changes or [], sort_keys=True),
        )
        if key not in self._cache:
            self._cache[key] = self._compute(point, open_lines, out_buses, changes)
            if len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        self._cache.move_to_end(key)
        return self._cache[key]

    def _compute(
        self, point: str, open_lines: list[str], out_buses: list[str], changes: list[dict] | None
    ) -> dict:
        _, edited, kept, _ = prepare_edits(
            self.world, point, open_lines, out_buses, allow_empty=True, changes=changes
        )
        settled, still_open = _after_cascade(edited.net, edited.point, kept)
        fed = {
            r["bus"]: r
            for r in dependency_workflow(edited.net, settled.gen, settled.load, settled.people, still_open)
        }
        nodes = {}
        for bus, row in criticality_workflow(edited.net, settled, still_open).items():
            key = f"B{bus:03d}"
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
