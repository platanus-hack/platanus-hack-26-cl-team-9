"""Adapter: PyPSA-CL model of the Ministerio de Energía (Topology.xlsx). Electrical parameters."""

from __future__ import annotations

import io
import logging
from typing import Any

from openpyxl import load_workbook

from cascadasen.domain.model import RawBranch, RawBus, RawPlant, RawStorage, SourceBundle, SourceInfo
from cascadasen.infrastructure.http import CachedHttp, FetchError
from cascadasen.infrastructure.sources.ide_energia import _mtime

log = logging.getLogger(__name__)
CACHE = "pypsa_cl/Topology.xlsx"


def _rows(wb, sheet: str) -> list[dict[str, Any]]:
    ws = wb[sheet]
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(it)]
    return [dict(zip(header, row, strict=False)) for row in it if any(v is not None for v in row)]


def _f(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


class PypsaClSource:
    source_id = "pypsa_cl"

    def __init__(self, http: CachedHttp, share_url: str, file_url: str) -> None:
        self.http = http
        self.share_url = share_url
        self.file_url = file_url

    def _download(self, refresh: bool) -> bytes:
        cached = self.http.cached(CACHE)
        if cached and not refresh:
            return cached.read_bytes()
        try:
            self.http.visit(self.share_url)  # the public sharing link sets the access cookie
            return self.http.get_bytes(self.file_url, CACHE, refresh=True)
        except FetchError:
            if cached:
                log.warning("PyPSA-CL download failed, using cached workbook")
                return cached.read_bytes()
            raise

    def contribute(self, bundle: SourceBundle, refresh: bool = False) -> SourceInfo:
        wb = load_workbook(io.BytesIO(self._download(refresh)), read_only=True, data_only=True)
        nodes = _rows(wb, "Nodes")
        for r in nodes:
            bundle.buses.append(
                RawBus(
                    self.source_id,
                    str(r["name"]),
                    _f(r.get("tension")),
                    _f(r.get("longitude")),
                    _f(r.get("latitude")),
                    r.get("comuna"),
                    r.get("region"),
                )
            )
        lines = _rows(wb, "Lines")
        for r in lines:
            if r.get("candidate") in (True, "True", 1):
                continue
            bundle.branches.append(
                RawBranch(
                    source=self.source_id,
                    name=str(r["name"]),
                    bus0=str(r["bus0"]),
                    bus1=str(r["bus1"]),
                    kv=_f(r.get("tension")),
                    s_nom_mva=_f(r.get("s_nom")),
                    r_ohm=_f(r.get("r [ohm]")),
                    x_ohm=_f(r.get("x [ohm]")),
                    r_pu=_f(r.get("r")),
                    x_pu=_f(r.get("x")),
                    build_year=_i(r.get("build_year")),
                    asset_type=r.get("Type of transmission asset"),
                )
            )
        gens = _rows(wb, "Generators")
        for k, r in enumerate(gens):
            if r.get("p_nom_extendable") in (True, "True", 1):
                continue
            bundle.model_generators.append(
                RawPlant(
                    source=self.source_id,
                    record_id=f"G{k}",
                    name=str(r.get("name") or ""),
                    tech=str(r.get("carrier") or ""),
                    mw=_f(r.get("p_nom")),
                    lon=_f(r.get("longitude")),
                    lat=_f(r.get("latitude")),
                    connection_bus=r.get("node"),
                    inertia_s=_f(r.get("inertia_contribution")),
                    build_year=_i(r.get("build_year")),
                    comuna_name=r.get("comuna"),
                )
            )
        storage = _rows(wb, "StorageUnits")
        for k, r in enumerate(storage):
            if r.get("p_nom_extendable") in (True, "True", 1):
                continue
            bundle.model_storage.append(
                RawStorage(
                    source=self.source_id,
                    record_id=f"S{k}",
                    name=str(r.get("name") or ""),
                    mw=_f(r.get("p_nom")),
                    hours=_f(r.get("max_hours")),
                    equipment=r.get("carrier"),
                    connection_bus=r.get("node"),
                    build_year=_i(r.get("build_year")),
                )
            )
        return SourceInfo(
            id=self.source_id,
            name="PyPSA-CL: modelo reducido del SEN (Topology.xlsx)",
            publisher="Ministerio de Energía (carpeta pública del modelo PyPSA-CL)",
            url=self.share_url,
            provides=(
                "barras con tensión y coordenadas",
                "líneas con r, x y capacidad (MVA)",
                "barra de conexión de generadores",
                "almacenamiento (MW, horas)",
            ),
            records=len(nodes) + len(lines) + len(gens) + len(storage),
            fetched_at=_mtime(self.http.cached(CACHE)),
            notes="Modelo de planificación de 234 barras; incluye obras futuras (build_year). Licencia no publicada.",
        )
