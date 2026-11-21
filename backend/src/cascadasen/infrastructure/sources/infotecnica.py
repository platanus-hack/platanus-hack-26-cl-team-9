"""Adapter: Coordinador Eléctrico Nacional, API Infotecnica. Official registry and line sections."""

from __future__ import annotations

from cascadasen.domain.model import RawBusbar, RawLine, RawPlant, RawSubstation, SourceBundle, SourceInfo
from cascadasen.domain.naming import parse_kv
from cascadasen.infrastructure.http import CachedHttp
from cascadasen.infrastructure.sources.ide_energia import _mtime


def line_key(nemotecnico: str | None) -> str | None:
    """'LT001CI1TR02----L0089' and 'LT001---------L0089' -> 'LT001L0089'."""
    if not nemotecnico or len(nemotecnico) < 10:
        return None
    return nemotecnico[:5] + nemotecnico[-5:]


class InfotecnicaSource:
    source_id = "cen_infotecnica"

    def __init__(self, http: CachedHttp, base_url: str) -> None:
        self.http = http
        self.base = base_url.rstrip("/")

    def _get(self, endpoint: str, refresh: bool) -> list[dict]:
        return self.http.get_json(f"{self.base}/{endpoint}/", f"{self.source_id}/{endpoint}.json", refresh)

    def contribute(self, bundle: SourceBundle, refresh: bool = False) -> SourceInfo:
        subs = self._get("subestaciones", refresh)
        for r in subs:
            bundle.cen_substations.append(
                RawSubstation(
                    source=self.source_id,
                    record_id=str(r["id"]),
                    name=(r.get("nombre") or "").strip(),
                    owner=r.get("propietario_nombre"),
                    cen_id=r["id"],
                    cen_code=r.get("nemotecnico"),
                    extra={k: r.get(k) for k in ("flag_scada", "flag_equipocom", "codigo")},
                )
            )
        bars = self._get("barras", refresh)
        for r in bars:
            if r.get("id_subestacion") is None:
                continue
            bundle.busbars.append(
                RawBusbar(
                    self.source_id,
                    str(r["id"]),
                    r["id_subestacion"],
                    r.get("nombre") or "",
                    parse_kv(r.get("nombre")),
                )
            )
        lines = self._get("lineas", refresh)
        for r in lines:
            key = line_key(r.get("nemotecnico"))
            if key:
                bundle.cen_lines[key] = {
                    "id": r["id"],
                    "nombre": r.get("nombre"),
                    "propietario": r.get("propietario_nombre"),
                }
        sections = self._get("tramos", refresh)
        for r in sections:
            bundle.cen_sections.append(
                RawLine(
                    source=self.source_id,
                    record_id=str(r["id"]),
                    name=(r.get("nombre") or "").strip(),
                    kv=parse_kv(r.get("nombre")),
                    circuit=r.get("circuito_nombre"),
                    owner=r.get("propietario_nombre"),
                    end1=r.get("extremo1_descripcion"),
                    end2=r.get("extremo2_descripcion"),
                    line_code=line_key(r.get("nemotecnico")),
                    extra={"nemotecnico": r.get("nemotecnico"), "tipo": r.get("tramo_tipo_nombre")},
                )
            )
        plants = self._get("centrales", refresh)
        for r in plants:
            bundle.cen_plants.append(
                RawPlant(
                    source=self.source_id,
                    record_id=str(r["id"]),
                    name=(r.get("nombre") or "").strip(),
                    tech=r.get("central_tipo_nombre"),
                    owner=r.get("propietario_nombre"),
                    comuna_name=r.get("comuna_nombre"),
                    extra={"nemotecnico": r.get("nemotecnico"), "region": r.get("region_nombre")},
                )
            )
        return SourceInfo(
            id=self.source_id,
            name="Infotecnica: registro técnico del SEN",
            publisher="Coordinador Eléctrico Nacional (CEN)",
            url=self.base,
            provides=(
                "ids y códigos oficiales de subestaciones",
                "barras y niveles de tensión",
                "tramos con extremos",
                "centrales",
            ),
            records=len(subs) + len(bars) + len(lines) + len(sections) + len(plants),
            fetched_at=_mtime(self.http.cached(f"{self.source_id}/tramos.json")),
            notes="Sin coordenadas ni parámetros eléctricos. Los tramos declaran sus extremos (paño, tap o punto).",
        )
