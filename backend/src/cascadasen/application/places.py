"""Resolve a place a person names to one bus of the 188-bus network (docs/stress.md section 3).

Why: "agrega un datacenter en Iquique" must land at the substation that supplies Iquique. Matching the text
against area names first sent it to the anchor of the area "Arica–Iquique", a mine 150 km inland, and
"Antofagasta" to S/E Escondida, 140 km away, even though S/E ANTOFAGASTA exists.

Order: a bus id, an area id, a substation name, a comuna (the substation that serves most of its people), a
province or region (its most populous comuna), an area name (its anchor bus), a unique part of a substation
name. Each answer says how it was resolved, so the model and the person can see where the point went.
"""

from __future__ import annotations

import difflib
import math
import re
import unicodedata
from typing import Any

from cascadasen.application.grids import GridError
from cascadasen.domain.cascade.network import bus_id

PREFIXES = (
    "cerca de ",
    "en ",
    "la comuna de ",
    "comuna de ",
    "la ciudad de ",
    "ciudad de ",
    "la region de ",
    "region de ",
    "la region ",
    "region ",
    "la provincia de ",
    "provincia de ",
    "subestacion ",
    "s/e ",
    "se ",
)
# Short names people use for regions whose official name (INE, in the comunas) is longer.
REGION_ALIASES = {
    "metropolitana": "metropolitana de santiago",
    "rm": "metropolitana de santiago",
    "araucania": "la araucania",
    "o'higgins": "libertador general bernardo o'higgins",
    "ohiggins": "libertador general bernardo o'higgins",
    "aysen": "aysen del general carlos ibanez del campo",
    "arica": "arica y parinacota",
}
# The largest gap between a SEN comuna's centroid and its main substation is 150 km (San Pedro de Atacama);
# the islands are 705 km (Juan Fernández) and 3,734 km (Isla de Pascua) away.
MAX_SERVING_KM = 300.0
BUS_ID = re.compile(r"^b\d{3,}$")
AREA_ID = re.compile(r"^a\d{2}$")


def fold(text: str) -> str:
    """Lowercase without accents and with single spaces, for matching what a person typed."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return " ".join(plain.split())


def bus_key(name: str) -> str:
    """A substation name without the "S/E" prefix and the owner in parentheses: "S/E CONCEPCION (FFCC)" ->
    "concepcion"."""
    key = re.sub(r"\([^)]*\)", " ", fold(name))
    return " ".join(key.removeprefix("s/e ").split())


def clean(text: str) -> str:
    key = fold(text.strip().strip("¿?¡!.,;:\"'"))
    changed = True
    while changed:
        changed = False
        for prefix in PREFIXES:
            if key.startswith(prefix) and len(key) > len(prefix):
                key, changed = key[len(prefix) :].strip(), True
    return key


def resolve_place(ctx: Any, text: str) -> dict[str, Any]:
    """One bus for `text`, with how it was found. `ctx` is the prepared-scenario context of `grid_stress`
    (bus names and kV, areas with their anchor bus, comunas with the substations that serve them)."""
    key = clean(text)
    if not key:
        raise GridError(
            "invalid", "Indica un lugar: una comuna, una subestación, un área A01-A13 o una barra B###."
        )
    steps = (
        _by_id,
        _by_bus_name,
        _by_comuna,
        _by_owned_bus_name,
        _by_province_or_region,
        _by_area_name,
        _by_partial_name,
    )
    for step in steps:
        found = step(ctx, key)
        if found is not None:
            return _answer(ctx, text, *found)
    known = sorted(set(_comunas(ctx)["comuna"]) | {bus_key(n) for n in ctx.names})
    near = difflib.get_close_matches(key, known, n=4, cutoff=0.75)
    hint = f" ¿Quisiste decir {', '.join(near)}?" if near else ""
    raise GridError(
        "not_found",
        f"No encuentro el lugar '{text}'.{hint} Usa una comuna, una subestación (S/E …), un área A01-A13 o una "
        "barra B###.",
    )


Found = tuple[int, str] | None  # bus index and how it was found


def _by_id(ctx: Any, key: str) -> Found:
    if BUS_ID.match(key) and int(key[1:]) < len(ctx.names):
        return int(key[1:]), "barra indicada por id"
    area = ctx.net.areas.get(key.upper()) if AREA_ID.match(key) else None
    if area is not None and area.anchor_bus is not None:
        return area.anchor_bus, f"barra principal del área {area.id} ({area.name})"
    return None


def _by_bus_name(ctx: Any, key: str) -> Found:
    """A substation named exactly so ("S/E CONCEPCION"). One with an owner in parentheses ("S/E PUENTE ALTO
    (CMPC)", a paper mill) only matches after the comunas, so the comuna of that name wins."""
    return _exact_bus(ctx, key, owned=False)


def _by_owned_bus_name(ctx: Any, key: str) -> Found:
    return _exact_bus(ctx, key, owned=True)


def _exact_bus(ctx: Any, key: str, owned: bool) -> Found:
    names, kv = ctx.names, ctx.net.buses.kv
    exact = [i for i in range(len(names)) if bus_key(names[i]) == key and ("(" in names[i]) == owned]
    if not exact:
        return None
    best = min(exact, key=lambda i: (-float(kv[i]), i))  # the highest voltage
    return best, f"subestación {names[best]}"


def _by_comuna(ctx: Any, key: str) -> Found:
    comuna = _comunas(ctx)["comuna"].get(key)
    if comuna is None:
        return None
    hit = _serving_bus(ctx, comuna)
    if hit is None:  # Magallanes, Aysén, Isla de Pascua: medium systems outside the SEN
        raise GridError(
            "not_found",
            f"La comuna de {comuna['name']} no está conectada al Sistema Eléctrico Nacional (es un sistema "
            "aislado), así que la red simulada no la incluye.",
        )
    return hit[0], f"subestación que abastece a la comuna de {comuna['name']} ({hit[1]:.0%} de su población)"


def _by_province_or_region(ctx: Any, key: str) -> Found:
    # a region first: "Biobío" is the region (Concepción) more often than the province (Los Ángeles)
    for kind, label in (("region", "región"), ("province", "provincia")):
        group = _comunas(ctx)[kind].get(key)
        if not group:
            continue
        top = max(group, key=lambda c: c["population"])
        hit = _serving_bus(ctx, top)
        if hit is not None:
            return hit[0], f"{label}: subestación de su comuna más poblada ({top['name']})"
    return None


def _by_area_name(ctx: Any, key: str) -> Found:
    for area in ctx.net.areas.values():
        if key in fold(area.name) and area.anchor_bus is not None:
            return area.anchor_bus, f"barra principal del área {area.id} ({area.name})"
    return None


def _by_partial_name(ctx: Any, key: str) -> Found:
    names = ctx.names
    partial = [i for i in range(len(names)) if key in bus_key(names[i])]
    if len(partial) > 1:
        shown = ", ".join(f"{bus_id(i)} {names[i]}" for i in partial[:8])
        raise GridError("not_found", f"'{key}' coincide con varias subestaciones: {shown}. Indica cuál.")
    return (partial[0], f"subestación {names[partial[0]]}") if partial else None


def _answer(ctx: Any, text: str, bus: int, how: str) -> dict[str, Any]:
    area = ctx.net.areas.get(ctx.area[bus])
    return {
        "place": text,
        "bus": bus_id(bus),
        "bus_name": ctx.names[bus],
        "area": ctx.area[bus],
        "area_name": area.name if area else None,
        "how": how,
    }


def _serving_bus(ctx: Any, comuna: dict) -> tuple[int, float] | None:
    """The bus behind the substation that serves the largest share of the comuna's people. None when that bus
    is over MAX_SERVING_KM from the comuna: the snapshot assigns the islands (Isla de Pascua, Juan Fernández)
    to a mainland substation, but they are not on the SEN."""
    for s in sorted(comuna.get("served_by", []), key=lambda s: -float(s.get("population", 0))):
        if s["node"] in ctx.node_bus:
            bus = ctx.node_bus[s["node"]]
            far = comuna.get("centroid") and _km(comuna["centroid"], ctx, bus) > MAX_SERVING_KM
            return None if far else (bus, float(s.get("share", 0.0)))
    return None


def _km(lon_lat: list[float], ctx: Any, bus: int) -> float:
    lat0 = math.radians(lon_lat[1])
    dx = (float(ctx.net.buses.lon[bus]) - lon_lat[0]) * math.cos(lat0)
    dy = float(ctx.net.buses.lat[bus]) - lon_lat[1]
    return 111.2 * math.hypot(dx, dy)


def _comunas(ctx: Any) -> dict[str, dict]:
    """Comunas by folded name, and the comunas of each province and region. Cached on the context."""
    cached = getattr(ctx, "_places", None)
    if cached is not None:
        return cached
    out: dict[str, dict] = {"comuna": {}, "province": {}, "region": {}}
    seen = {id(c): c for c in ctx.comunas.values()}
    for c in seen.values():
        out["comuna"][fold(c["name"])] = c
        for kind, field in (("province", "province_name"), ("region", "region_name")):
            if c.get(field):
                out[kind].setdefault(fold(c[field]), []).append(c)
    for alias, official in REGION_ALIASES.items():
        if official in out["region"]:
            out["region"].setdefault(alias, out["region"][official])
    ctx._places = out
    return out
