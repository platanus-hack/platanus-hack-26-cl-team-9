"""Composition root: wires adapters into the ports used by the application."""

from __future__ import annotations

from cascadasen.application.build_grid import BuildGridSnapshot
from cascadasen.application.build_regional import BuildRegionalGrid
from cascadasen.domain.ports import RegionalGridSource
from cascadasen.domain.unify import GridUnifier
from cascadasen.infrastructure.exporters import StaticFilesExporter
from cascadasen.infrastructure.http import CachedHttp
from cascadasen.infrastructure.settings import Settings
from cascadasen.infrastructure.snapshot_repository import JsonSnapshotRepository
from cascadasen.infrastructure.sources.ide_energia import IdeEnergiaSource
from cascadasen.infrastructure.sources.ine_censo import IneCensoSource
from cascadasen.infrastructure.sources.infotecnica import InfotecnicaSource
from cascadasen.infrastructure.sources.pypsa_cl import PypsaClSource
from cascadasen.infrastructure.sources.regional.energia_argentina import EnergiaArgentinaSource
from cascadasen.infrastructure.sources.regional.epe_brasil import EpeBrasilSource
from cascadasen.infrastructure.sources.regional.osinergmin_peru import OsinergminPeruSource
from cascadasen.infrastructure.sources.regional.osm_overpass import OsmOverpassSource


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


DEFAULT_COUNTRIES = ("BRA", "PER", "ARG", "BOL")
OSM_COUNTRIES = {
    "BRA": ("Brasil", "BR"),
    "PER": ("Perú", "PE"),
    "ARG": ("Argentina", "AR"),
    "BOL": ("Bolivia", "BO"),
}


def regional_use_case(settings: Settings, osm: set[str] | None = None) -> BuildRegionalGrid:
    """Official source per country (Bolivia has none: OpenStreetMap); `osm` forces OSM for other countries."""
    http = CachedHttp(settings.raw_dir, settings.http_timeout_s, settings.user_agent)
    official: dict[str, RegionalGridSource] = {
        "BRA": EpeBrasilSource(http, settings.epe_webmap_url),
        "PER": OsinergminPeruSource(http, settings.osinergmin_url),
        "ARG": EnergiaArgentinaSource(http, settings.energia_ar_url),
    }
    sources: dict[str, RegionalGridSource] = {}
    for iso, (name, iso2) in OSM_COUNTRIES.items():
        use_osm = iso == "BOL" or iso in (osm or set())
        sources[iso] = (
            OsmOverpassSource(http, iso, name, iso2, settings.overpass_url) if use_osm else official[iso]
        )
    return BuildRegionalGrid(sources, settings.regional_dir)
