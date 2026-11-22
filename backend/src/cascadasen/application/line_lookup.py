"""Find a transmission line of the 188-bus network by the name a person gives it (docs/stress.md section 3).

Why: "corta la línea Nueva Maitencillo – Nueva Pan de Azúcar" needs the id R239, and nothing resolved a line by
name: the assistant walked the network area by area with `describe_network` and ran out of steps. A line has no
name of its own in the reduced network; it is named by its two end substations, as the web does.

Lookup only (docs/cyber.md section 8): the answer lists the lines that match the name, in id order. It never
ranks lines, never says which one matters most and never suggests a line the person did not name.
"""

from __future__ import annotations

import re
from typing import Any

from cascadasen.application.grids import GridError
from cascadasen.application.places import bus_key, clean, fold

MAX_MATCHES = 12
LINE_ID = re.compile(r"^[ru]\d{3,}$")
KV = re.compile(r"\(?\b(\d{2,3})\s*kv\b\)?")
LINE_PREFIXES = ("la linea ", "linea ", "la línea ", "línea ", "el tramo ", "tramo ", "entre ")
# Between the two end names: an en or em dash, a hyphen or a slash with spaces ("S/E" keeps its slash), "a",
# "y", "hasta", "con".
SEPARATOR = re.compile(r"\s*[–—]\s*|\s+-\s+|\s+(?:a|y|hasta|con)\s+|\s+/\s+")


def find_lines(ctx: Any, text: str) -> dict[str, Any]:
    """The lines whose name matches `text`: a line id (R###), "A – B" or "entre A y B" (both end substations,
    in either order), or one substation name (every line that ends there). A voltage in the text ("500 kV")
    narrows the answer. `ctx` is the prepared-scenario context of `grid_stress` (bus names and the network)."""
    key = fold(text.strip().strip("¿?¡!.,;:\"'"))
    for prefix in LINE_PREFIXES:
        key = key.removeprefix(fold(prefix))
    kv_match = KV.search(key)
    kv = float(kv_match.group(1)) if kv_match else None
    key = " ".join(KV.sub(" ", key).split())
    if not key:
        raise GridError(
            "invalid",
            "Indica la línea: su id R### o sus dos subestaciones, por ejemplo «Ancoa – Alto Jahuel».",
        )
    lines = ctx.net.buses.lines
    if LINE_ID.match(key):
        found = [ln for ln in lines if ln.id == key.upper()]
        if not found:
            raise GridError("not_found", f"No existe la línea {key.upper()}.")
        return _answer(ctx, text, found, "línea indicada por id")
    pair = _two_ends(ctx, key)
    if pair is not None:
        a, b = pair
        found = [ln for ln in lines if (ln.a in a and ln.b in b) or (ln.a in b and ln.b in a)]
        how = f"líneas entre {_names(ctx, a)} y {_names(ctx, b)}"
        if not found:
            raise GridError(
                "not_found",
                f"No hay una línea directa entre {_names(ctx, a)} y {_names(ctx, b)} en la red de 188 barras. "
                "Prueba con una sola subestación para ver las líneas que llegan a ella.",
            )
    else:
        a = _end_buses(ctx, key)
        found = [ln for ln in lines if ln.a in a or ln.b in a]
        how = f"líneas que llegan a {_names(ctx, a)}"
    if kv is not None:
        found = [ln for ln in found if abs(float(ln.kv) - kv) < 1e-6] or found
    return _answer(ctx, text, found, how)


def _two_ends(ctx: Any, key: str) -> tuple[set[int], set[int]] | None:
    """The buses of both ends when `key` names two substations, or None when it names one. Each separator is
    tried in turn, so a substation name that contains " y " or " a " still resolves. A key with a separator
    whose ends never resolve raises the error of the first split."""
    if any(bus_key(n) == bus_key(clean(key)) for n in ctx.names):
        return None
    first: GridError | None = None
    splits = (SEPARATOR.match(key, pos) for pos in range(len(key)))  # overlapping: "s/e a / s/e b"
    for m in (m for m in splits if m):
        left, right = key[: m.start()].strip(), key[m.end() :].strip()
        if not left or not right:
            continue
        try:
            return _end_buses(ctx, left), _end_buses(ctx, right)
        except GridError as exc:
            first = first or exc
    if first is not None:
        raise first
    return None


def _end_buses(ctx: Any, text: str) -> set[int]:
    """Buses whose substation name is `text` exactly ("Maitencillo" is S/E MAITENCILLO, not S/E NUEVA
    MAITENCILLO), else those whose name contains it."""
    key = bus_key(clean(text))
    keys = [bus_key(n) for n in ctx.names]
    exact = {i for i, k in enumerate(keys) if k == key}
    if exact:
        return exact
    partial = {i for i, k in enumerate(keys) if key and key in k}
    if partial:
        return partial
    raise GridError(
        "not_found",
        f"No encuentro la subestación '{text.strip()}' en la red de 188 barras. Usa el nombre de una subestación "
        "(S/E …) o el id de la línea.",
    )


def _names(ctx: Any, buses: set[int]) -> str:
    shown = sorted(buses)[:3]
    more = f" y {len(buses) - 3} más" if len(buses) > 3 else ""
    return ", ".join(ctx.names[i] for i in shown) + more


def _answer(ctx: Any, text: str, found: list, how: str) -> dict[str, Any]:
    ordered = sorted(found, key=lambda ln: ln.id)  # id order: a lookup, never a ranking
    names = ctx.names
    return {
        "query": text,
        "how": how,
        "matched": len(ordered),
        "lines": [
            {
                "id": ln.id,
                "name": f"{names[ln.a]} – {names[ln.b]} ({float(ln.kv):g} kV)",
                "kv": float(ln.kv),
                "a": f"B{ln.a:03d}",
                "b": f"B{ln.b:03d}",
                "capacity_mw": round(float(ln.capacity_mw), 1),
            }
            for ln in ordered[:MAX_MATCHES]
        ],
        "truncated": len(ordered) > MAX_MATCHES,
    }
