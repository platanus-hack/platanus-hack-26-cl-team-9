"""Adapter: ONS Dados Abertos (Brazil), transmission lines and substations with bus numbers (CC BY).

`LINHA_TRANSMISSAO.csv` gives every line from 230 kV with its two bus numbers, positive-sequence r, x
and shunt, and its rating in amperes. `SUBESTACAO.csv` gives every busbar from 69 kV with its substation
and coordinates. Both are `;`-separated UTF-8 with space-padded text fields.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from cascadasen.domain.regional import RegionalSource
from cascadasen.domain.regional_network import OnsBusbar, OnsDataset, OnsLine
from cascadasen.infrastructure.http import CachedHttp

LINES_CACHE = "regional/bra/ons_linha_transmissao.csv"
SUBSTATIONS_CACHE = "regional/bra/ons_subestacao.csv"
CAPACITY_COLUMN = "val_capacoperlongacomlimit"  # long duration, with limiting factor (docs/regional.md)


def _text(row: dict[str, str | None], key: str) -> str:
    return (row.get(key) or "").strip()


def _num(row: dict[str, str | None], key: str) -> float | None:
    raw = _text(row, key).replace(",", ".")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _kind(raw: str) -> str:
    up = raw.upper()
    if "DC" in up.split():
        return "dc"
    if "RAMAL" in up:
        return "ramal"
    return "ac"


def _rows(data: bytes) -> list[dict[str, str | None]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


def parse_lines(data: bytes) -> list[OnsLine]:
    out = []
    for row in _rows(data):
        kv = _num(row, "val_niveltensao_kv")
        if kv is None:
            continue
        out.append(
            OnsLine(
                record=_text(row, "cod_equipamento") or _text(row, "nom_linhadetransmissao"),
                name=" ".join(_text(row, "nom_linhadetransmissao").split()),
                kind=_kind(_text(row, "nom_tipolinha")),
                kv=kv,
                length_km=_num(row, "val_comprimento"),
                r_pct=_num(row, "val_resistencia"),
                x_pct=_num(row, "val_reatancia"),
                shunt_mvar=_num(row, "val_shunt"),
                amps=_num(row, CAPACITY_COLUMN),
                bus_from=_text(row, "num_barra_de"),
                bus_to=_text(row, "num_barra_para"),
                sub_from=_text(row, "nom_subestacao_de"),
                sub_to=_text(row, "nom_subestacao_para"),
                entered=_text(row, "dat_entradaoperacao") or None,
                deactivated=_text(row, "dat_desativacao") or None,
            )
        )
    return out


def parse_busbars(data: bytes) -> list[OnsBusbar]:
    out = []
    for row in _rows(data):
        number = _text(row, "num_barra")
        if not number:
            continue
        lat, lon = _num(row, "val_latitude"), _num(row, "val_longitude")
        if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
            lat = lon = None
        out.append(
            OnsBusbar(
                number=number,
                substation=_text(row, "id_subestacao"),
                name=_text(row, "nom_subestacao"),
                kv=_num(row, "val_niveltensao"),
                lat=lat,
                lon=lon,
            )
        )
    return out


class OnsBrasilSource:
    country = "BRA"

    def __init__(self, http: CachedHttp, lines_url: str, substations_url: str) -> None:
        self.http = http
        self.lines_url = lines_url
        self.substations_url = substations_url

    def fetch(self, refresh: bool = False) -> OnsDataset:
        lines = parse_lines(self.http.get_bytes(self.lines_url, LINES_CACHE, refresh))
        busbars = parse_busbars(self.http.get_bytes(self.substations_url, SUBSTATIONS_CACHE, refresh))
        now = datetime.now(UTC).isoformat(timespec="seconds")
        licence = "CC BY (Creative Commons Atribuição), ONS Dados Abertos"
        sources = [
            RegionalSource(
                id="ons_linha_transmissao",
                name="ONS, linhas de transmissão da rede de operação",
                publisher="Operador Nacional do Sistema Elétrico (ONS), Brasil",
                url=self.lines_url,
                license=licence,
                attribution="ONS Dados Abertos",
                provides=("lines",),
                fetched_at=now,
            ),
            RegionalSource(
                id="ons_subestacao",
                name="ONS, subestações da rede de operação",
                publisher="Operador Nacional do Sistema Elétrico (ONS), Brasil",
                url=self.substations_url,
                license=licence,
                attribution="ONS Dados Abertos",
                provides=("substations",),
                fetched_at=now,
            ),
        ]
        return OnsDataset(lines, busbars, sources)
