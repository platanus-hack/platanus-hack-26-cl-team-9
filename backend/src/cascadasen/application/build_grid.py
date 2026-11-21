"""Use case: fetch every source, unify, validate, persist and export."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from cascadasen.domain.model import GridSnapshot, SourceBundle, SourceInfo
from cascadasen.domain.ports import ContractExporter, GridDataSource, SnapshotRepository
from cascadasen.domain.unify import GridUnifier
from cascadasen.domain.validation import validate_snapshot

log = logging.getLogger(__name__)


@dataclass
class BuildGridSnapshot:
    sources: Sequence[GridDataSource]
    unifier: GridUnifier
    repository: SnapshotRepository
    exporters: Sequence[ContractExporter] = ()
    required: frozenset[str] = field(default_factory=lambda: frozenset({"ide_energia"}))

    def execute(self, refresh: bool = False) -> GridSnapshot:
        bundle = SourceBundle()
        for src in self.sources:
            try:
                info = src.contribute(bundle, refresh=refresh)
                log.info("source %s: %d records", info.id, info.records)
            except Exception as exc:
                if src.source_id in self.required:
                    raise
                log.warning("source %s unavailable: %s", src.source_id, exc)
                info = SourceInfo(
                    src.source_id, src.source_id, "", "", (), notes=f"no disponible en este build: {exc}"
                )
            bundle.sources.append(info)
        snapshot = self.unifier.unify(bundle)
        snapshot.stats["validation"] = validate_snapshot(snapshot)
        self.repository.save(snapshot)
        for exporter in self.exporters:
            for path in exporter.export(snapshot):
                log.info("exported %s", path)
        return snapshot
