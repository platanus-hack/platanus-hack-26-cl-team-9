"""cascadasen-sim-fixtures: precompute strategic runs on the mapa 3 network for the offline demo.

The live API (`/api/v1/sim/*`) gives a new random run every time; these files are the fallback when
there is no server, next to the mapa 3 cut cache. Layout under `web/public/cache/theater/` (git-ignored):

    index.json                                points, runs (file, point, template, policy, seed, adversary)
    catalog.json, narrative_es.json           choices and Spanish narration templates
    network-<point>.json                      mapa 3 network + areas, corridors and defences (GET /sim/network)
    <point>/<template>-<policy>-s<seed>.json  recipe, every cycle snapshot, report and after-action
    campaign-<point>.json                     flagship campaign (policies x static/adaptive adversary)

The files are generated: regenerate them, do not edit them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cascadasen.application.run_campaign import CampaignSpec
from cascadasen.application.simulation_service import SimulationService
from cascadasen.application.theater_world import ProcessedWorld
from cascadasen.domain.simulation.timeline import NOTICE
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig
from cascadasen.domain.theater.narrative import templates
from cascadasen.infrastructure.container import repository
from cascadasen.infrastructure.settings import REPO_ROOT, get_settings

DEFAULT_POINTS = ("nov2026-1300", "feb2025-1500")
TEMPLATE = "flagship_observability"


def _write(path: Path, data: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return f"{path} ({path.stat().st_size // 1024} KB)"


def build_theater_cache(
    sim: SimulationService,
    out: Path,
    points: list[str],
    seed: int,
    campaign: bool = True,
    template: str = TEMPLATE,
) -> list[str]:
    written = [_write(out / "catalog.json", sim.catalog()), _write(out / "narrative_es.json", templates())]
    adversary = AdversaryConfig(True, "reduce_observability", 8, True)
    runs = []
    for point in points:
        written.append(_write(out / f"network-{point}.json", sim.theater_network(point)))
        for policy in ("A", "B", "C"):
            config = RunConfig(
                template=template, policy=policy, seed=seed, operating_point=point, adversary=adversary
            )
            summary = sim.runs.create(config, auto_run=True)
            rid = summary["run_id"]
            run = sim.runs.get(rid)
            name = f"{point}/{template}-{policy}-s{seed}.json"
            written.append(
                _write(
                    out / name,
                    {
                        "run": summary,
                        "recipe": run.recipe(),
                        "snapshots": run.snapshots,
                        "report": sim.runs.report(rid),
                        "after_action": sim.runs.after_action(rid),
                        "trace_head": run.log.head,
                    },
                )
            )
            runs.append(
                {
                    "file": name,
                    "point": point,
                    "template": template,
                    "policy": policy,
                    "seed": seed,
                    "adversary": {"objective": adversary.objective, "adaptive": adversary.adaptive},
                }
            )
        if campaign:
            spec = CampaignSpec(mode="adversarial", seeds=(1, 2, 3), uncertainty_levels=(1.0,), point=point)
            written.append(_write(out / f"campaign-{point}.json", sim.campaigns.run(spec)))
    written.append(_write(out / "index.json", {"points": points, "runs": runs, "notice": NOTICE}))
    return written


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Precalcula corridas del teatro sobre la red del mapa 3.")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "web" / "public" / "cache" / "theater")
    parser.add_argument("--point", action="append", help="punto de operación del mapa 3 (repetible)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-campaign", action="store_true")
    args = parser.parse_args()
    snapshot = repository(settings).load()
    if snapshot is None:
        print("No hay snapshot: ejecuta cascadasen-build primero.")
        return 1
    world = ProcessedWorld(settings.processed_dir)
    sim = SimulationService.from_snapshot(snapshot, world=world)
    points = args.point or [p for p in DEFAULT_POINTS if p in world.points()]
    print("\n".join(build_theater_cache(sim, args.out, points, args.seed, not args.no_campaign)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
