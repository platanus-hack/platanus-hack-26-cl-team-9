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


def usd_m(usd: float) -> str:
    return f"US$ {usd / 1e6:,.1f} M".replace(",", "_").replace(".", ",").replace("_", ".")


def format_cost(r: HealthReport) -> str | None:
    """Cost line next to the index: a regulatory valuation, never a measured loss."""
    cost = r.extra.get("cost")
    if not cost:
        return None
    hours = f"{cost['outage_duration_h']['value']:g} h supuestas"
    if r.kind == "prefault":
        return (
            f"  $ Dinero en riesgo N-1 (modelo): esperado {usd_m(cost['n1_expected_cost_usd'])}, "
            f"peor {usd_m(cost['n1_worst_cost_usd'])}; {cost['n1_cuts_with_cost']} de {cost['n1_cuts']} cortes "
            f"con costo, los {cost['n1_cost_share']['count']} más caros suman {cost['n1_cost_share']['share_band']} "
            f"(costo de falla CNE [19], {hours}, mismo peso por línea)"
        )
    floor = "; piso, no estimación" if cost["is_floor"] else ""
    return f"  $ Costo estimado: {usd_m(cost['cost_usd'])} (costo de falla CNE [19], {hours}{floor})"


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
    cost = format_cost(r)
    if cost:
        lines.append(cost)
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
            "\n$ valoración regulatoria (costo de falla CNE), no pérdida medida; no entra en el índice."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
