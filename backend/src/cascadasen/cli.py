"""cascadasen-build: download (or reuse cached) sources and write the unified grid snapshot."""

from __future__ import annotations

import argparse
import json
import logging

from cascadasen.infrastructure.container import build_use_case
from cascadasen.infrastructure.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Construye la red unificada del SEN desde las fuentes públicas."
    )
    parser.add_argument("--refresh", action="store_true", help="vuelve a descargar todas las fuentes")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    snapshot = build_use_case(settings).execute(refresh=args.refresh)
    summary = {k: v for k, v in snapshot.stats.items() if k != "validation"}
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print("validación:", json.dumps(snapshot.stats["validation"]["summary"], ensure_ascii=False))
    for c in snapshot.stats["validation"]["checks"]:
        print(f"  [{c['status']:4}] {c['title']}: {c['value']} (esperado {c['expected']})")
    print(f"snapshot: {settings.snapshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
