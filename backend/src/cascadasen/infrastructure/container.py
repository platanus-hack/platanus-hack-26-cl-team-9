"""Composition root: wires adapters into the ports used by the application."""

from __future__ import annotations

from cascadasen.application.build_grid import BuildGridSnapshot
from cascadasen.domain.unify import GridUnifier
from cascadasen.infrastructure.exporters import StaticFilesExporter
from cascadasen.infrastructure.http import CachedHttp
from cascadasen.infrastructure.settings import Settings
from cascadasen.infrastructure.snapshot_repository import JsonSnapshotRepository
from cascadasen.infrastructure.sources.ide_energia import IdeEnergiaSource
from cascadasen.infrastructure.sources.ine_censo import IneCensoSource
from cascadasen.infrastructure.sources.infotecnica import InfotecnicaSource
from cascadasen.infrastructure.sources.pypsa_cl import PypsaClSource


def repository(settings: Settings) -> JsonSnapshotRepository:
    return JsonSnapshotRepository(settings.snapshot_path)


def build_use_case(settings: Settings) -> BuildGridSnapshot:
    http = CachedHttp(settings.raw_dir, settings.http_timeout_s, settings.user_agent)
    sources = [
        IdeEnergiaSource(http, settings.ide_energia_url),
        InfotecnicaSource(http, settings.infotecnica_url),
        PypsaClSource(http, settings.pypsa_share_url, settings.pypsa_file_url),
        IneCensoSource(http, settings.census_url),
    ]
    return BuildGridSnapshot(
        sources=sources,
        unifier=GridUnifier(),
        repository=repository(settings),
        exporters=[StaticFilesExporter(settings.processed_dir)],
    )
