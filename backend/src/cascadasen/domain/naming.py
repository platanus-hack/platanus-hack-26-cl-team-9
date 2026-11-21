"""Name normalization and matching for substations, lines and plants.

Chilean grid names come in many spellings across sources ("S/E POLPAICO (TRANSELEC)",
"Polpaico 220kV", "S/E POLPAICO_220"). Everything is compared after `norm`.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

VOLT_RE = re.compile(r"\b\d+([.,]\d+)?\s*K\s*V\b|\b\d+\s*HZ\b|_\d+(\.\d+)?$")
NOISE_RE = re.compile(r"\b(S/E|SE|PA|L\d|C\d|CIRCUITO \d|TRAMO \d)\b")
PAREN_RE = re.compile(r"\(.*?\)")
TAP_RE = re.compile(r"\bTAP\b|SECCIONADORA")
KV_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*K\s*V\b", re.IGNORECASE)
BAY_RE = re.compile(r"\s+[A-Z]{1,2}\d{1,3}[A-Z]?$")


def ascii_upper(text: str | None) -> str:
    s = (text or "").replace("–", "-").replace("—", "-")  # before the ASCII fold drops them
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def norm(text: str | None) -> str:
    """Comparable form: ASCII upper case, no voltages, no S/E prefix, no circuit tokens."""
    s = ascii_upper(text)
    s = VOLT_RE.sub(" ", s)
    s = NOISE_RE.sub(" ", s)
    s = re.sub(r"[^A-Z0-9()' ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_parens(text: str) -> str:
    return re.sub(r"\s+", " ", PAREN_RE.sub(" ", text)).strip()


def strip_central(text: str) -> str:
    return text.removeprefix("CENTRAL ").strip()


def parse_kv(text: str | None) -> float | None:
    m = KV_RE.search(text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def line_ends(name: str | None) -> list[str]:
    """'ANCOA - ALTO JAHUEL 500KV L1' -> ['ANCOA', 'ALTO JAHUEL']."""
    raw = ascii_upper(name)
    parts = [p for p in re.split(r"\s+-\s+|\s-|-\s", raw) if p.strip()]
    if len(parts) < 2:
        return [norm(raw)]
    return [norm(parts[0]), norm(parts[-1])]


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    a2, b2 = strip_parens(a), strip_parens(b)
    if a2 and b2 and (a2 != a or b2 != b):
        r = max(r, difflib.SequenceMatcher(None, a2, b2).ratio() - 0.03)
    return r


def name_score(candidate: str, targets: list[str]) -> float:
    """Best similarity of a substation name against any of the target names."""
    n = norm(candidate)
    n_short = strip_central(n)
    best = 0.0
    for t in targets:
        best = max(best, similarity(n, t), similarity(n_short, strip_central(t)))
    return best


def is_tap_name(name: str | None) -> bool:
    return bool(TAP_RE.search(norm(name)))


def bay_stripped(text: str) -> str:
    """'S/E OSORNO B3' -> 'S/E OSORNO' (drops the bay code of a paño description)."""
    return BAY_RE.sub("", text.strip())
