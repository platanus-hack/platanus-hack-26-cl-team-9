"""cascadasen-health: grid health index (margin to the limit) for operating points, before and after a cut.

Default compares the 25F reference (feb2025-1500) with the minimum-demand point of the same network
(feb2025-0300), before the fault and after cutting the 25F corridor (R239). See docs/health.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cascadasen.domain.cascade.health import HealthReport, event_health, prefault_health
from cascadasen.domain.cascade.scenario import load_network_and_point
from cascadasen.infrastructure.settings import get_settings

DEFAULT_POINTS = ["feb2025-1500", "feb2025-0300"]
DEFAULT_CUT = "R239"


def compare_workflow(processed: Path, point_ids: list[str], cut: list[str]) -> list[HealthReport]:
    """Why: tell how healthy each operating point is, before an event and after the cut."""
    reports: list[HealthReport] = []
    for pid in point_ids:
        net, op = load_network_and_point(processed, pid)
        reports.append(prefault_health(net, op))
        if cut:
            reports.append(event_health(net, op, cut))
    return reports


def format_report(r: HealthReport) -> str:
    title = "antes de la falla" if r.kind == "prefault" else f"después del corte {','.join(r.extra['cut'])}"
    flag = "  (INCIERTO: tensión no calculada)" if r.uncertain else ""
    lines = [f"{r.scenario} · {title}: índice {r.index:.2f}, limita {r.binding}{flag}"]
    for m in r.margins:
        mark = " " if m.in_index else "*"
        src = "supuesto" if m.is_assumption else (m.source or "")
        lines.append(
            f"  {mark} {m.label:<46} {m.value:4.2f} (bruto {m.raw:+.2f})  {m.measured}; límite {m.limit}  [{src}]"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Índice de salud de la red por margen al límite.")
    parser.add_argument("--points", nargs="+", default=DEFAULT_POINTS, help="ids de operating_points.json")
    parser.add_argument(
        "--cut", nargs="*", default=[DEFAULT_CUT], help="líneas a cortar (vacío: solo pre-falla)"
    )
    parser.add_argument("--json", action="store_true", help="emite los reportes como JSON")
    args = parser.parse_args()
    reports = compare_workflow(get_settings().processed_dir, args.points, args.cut)
    if args.json:
        print(json.dumps([r.as_dict() for r in reports], indent=1, ensure_ascii=False))
    else:
        print("\n\n".join(format_report(r) for r in reports))
        print(
            "\n* informativa, no entra en el mínimo. El índice es un modelo propio, no un indicador oficial del CEN."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
