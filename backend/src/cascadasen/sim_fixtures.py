"""cascadasen-sim-fixtures: write simulation fixtures so the frontend can work without the API.

Writes the reduced network, the catalog, the Spanish narration, two 25F timelines, one flagship run
per policy (snapshots, report, after-action) and a flagship campaign. Output defaults to
`data/processed/sim/`; the files are generated, so regenerate them instead of editing them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cascadasen.application.run_campaign import CampaignSpec
from cascadasen.application.simulate import SimulateCommand
from cascadasen.application.simulation_service import SimulationService
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig
from cascadasen.domain.theater.narrative import templates
from cascadasen.infrastructure.container import repository
from cascadasen.infrastructure.settings import get_settings


def _write(out: Path, name: str, data: Any) -> str:
    path = out / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return f"{path} ({path.stat().st_size // 1024} KB)"


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Escribe fixtures de simulación para el frontend.")
    parser.add_argument("--out", type=Path, default=settings.processed_dir / "sim")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    snapshot = repository(settings).load()
    if snapshot is None:
        print("No hay snapshot: ejecuta cascadasen-build primero.")
        return 1
    sim = SimulationService.from_snapshot(snapshot)
    args.out.mkdir(parents=True, exist_ok=True)
    written = [
        _write(args.out, "network.json", sim.network_view()),
        _write(args.out, "catalog.json", sim.catalog()),
        _write(args.out, "narrative_es.json", templates()),
    ]
    for behavior, defenses in (("as_happened", "25F"), ("per_code", "implemented_dec2025")):
        tl = sim.simulate(SimulateCommand("25F", defenses, behavior, ["A06-A07/500"]))
        written.append(_write(args.out, f"timeline_25F_{behavior}.json", tl))
    adversary = AdversaryConfig(True, "reduce_observability", 8, False)
    for policy in ("A", "B", "C"):
        summary = sim.runs.create(
            RunConfig(template="flagship_observability", policy=policy, seed=args.seed, adversary=adversary),
            auto_run=True,
        )
        rid = summary["run_id"]
        run = sim.runs.get(rid)
        written.append(
            _write(
                args.out,
                f"run_flagship_{policy}.json",
                {
                    "run": summary,
                    "snapshots": run.snapshots,
                    "report": sim.runs.report(rid),
                    "after_action": sim.runs.after_action(rid),
                    "trace_head": run.log.head,
                },
            )
        )
    campaign = sim.campaigns.run(
        CampaignSpec(mode="adversarial", seeds=(1, 2, 3), uncertainty_levels=(1.0, 2.0))
    )
    written.append(_write(args.out, "campaign_flagship.json", campaign))
    print("\n".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
