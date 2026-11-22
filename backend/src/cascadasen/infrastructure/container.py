"""Composition root: wires adapters into the ports used by the application."""

from __future__ import annotations

from cascadasen.application.build_grid import BuildGridSnapshot
from cascadasen.application.build_regional import BuildFlowNetwork, BuildRegionalGrid
from cascadasen.domain.ports import DocumentStore, GridDataSource, GridStore, RegionalGridSource
from cascadasen.domain.unify import GridUnifier
from cascadasen.infrastructure.document_store import FileDocumentStore, MemoryDocumentStore, S3DocumentStore
from cascadasen.infrastructure.exporters import StaticFilesExporter
from cascadasen.infrastructure.grid_store import LocalGridStore, S3GridStore
from cascadasen.infrastructure.http import CachedHttp
from cascadasen.infrastructure.settings import Settings
from cascadasen.infrastructure.snapshot_repository import JsonSnapshotRepository
from cascadasen.infrastructure.sources.ide_energia import IdeEnergiaSource
from cascadasen.infrastructure.sources.ine_censo import IneCensoSource
from cascadasen.infrastructure.sources.infotecnica import InfotecnicaSource
from cascadasen.infrastructure.sources.pypsa_cl import PypsaClSource
from cascadasen.infrastructure.sources.regional.energia_argentina import EnergiaArgentinaSource
from cascadasen.infrastructure.sources.regional.epe_brasil import EpeBrasilSource
from cascadasen.infrastructure.sources.regional.ons_brasil import OnsBrasilSource
from cascadasen.infrastructure.sources.regional.osinergmin_peru import OsinergminPeruSource
from cascadasen.infrastructure.sources.regional.osm_overpass import OsmOverpassSource


def repository(settings: Settings) -> JsonSnapshotRepository:
    return JsonSnapshotRepository(settings.snapshot_path)


def build_use_case(settings: Settings) -> BuildGridSnapshot:
    http = CachedHttp(settings.raw_dir, settings.http_timeout_s, settings.user_agent)
    sources: list[GridDataSource] = [
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


def document_store(settings: Settings) -> DocumentStore:
    """Where sessions and run records live (`CASCADASEN_SESSION_STORE`)."""
    ttl_s = settings.session_ttl_s
    if settings.session_store == "file":
        return FileDocumentStore(settings.sessions_dir, ttl_s=ttl_s)
    if settings.session_store == "s3":
        if not settings.session_bucket:
            raise ValueError("CASCADASEN_SESSION_BUCKET is required when CASCADASEN_SESSION_STORE=s3")
        return S3DocumentStore(settings.session_bucket, settings.aws_region, settings.aws_profile)
    return MemoryDocumentStore(ttl_s=ttl_s)


def grid_store(settings: Settings) -> GridStore:
    """Where the grid documents are read from (`CASCADASEN_GRIDS_STORE`)."""
    if settings.grids_store == "s3":
        bucket = settings.grids_bucket or settings.session_bucket
        if not bucket:
            raise ValueError("CASCADASEN_GRIDS_BUCKET is required when CASCADASEN_GRIDS_STORE=s3")
        return S3GridStore(bucket, settings.grids_prefix, settings.aws_region, settings.aws_profile)
    return LocalGridStore(settings.grids_dir)


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


def flow_network_use_case(settings: Settings) -> BuildFlowNetwork:
    """Brazil's flow network: ONS lines and substations, with the EPE layer for plants and checks."""
    http = CachedHttp(settings.raw_dir, settings.http_timeout_s, settings.user_agent)
    return BuildFlowNetwork(
        OnsBrasilSource(http, settings.ons_lines_url, settings.ons_substations_url),
        EpeBrasilSource(http, settings.epe_webmap_url),
        settings.regional_dir,
    )
