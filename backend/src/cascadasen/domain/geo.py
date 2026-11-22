"""Small geometry toolkit (local equirectangular metres, UTM inverse, simplification)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

EARTH_R = 6371008.8


LON0 = -71.0  # central meridian for continental Chile (-76..-66)


def project(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Sinusoidal projection centred on LON0, in metres. Distances between nearby points are
    within ~2 % anywhere in Chile (the spurious east-west shift grows with |lon - LON0|)."""
    lat_r = np.radians(lat)
    return np.c_[EARTH_R * np.radians(np.asarray(lon) - LON0) * np.cos(lat_r), EARTH_R * lat_r]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a)) / 1000


def seg_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Distance from p to segment ab and the fraction t along it."""
    ab = b - a
    denom = float(ab @ ab)
    t = 0.0 if denom == 0 else float(np.clip((p - a) @ ab / denom, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab))), t


def douglas_peucker(xy: np.ndarray, tol: float) -> list[int]:
    if len(xy) <= 2:
        return list(range(len(xy)))
    keep = {0, len(xy) - 1}
    stack = [(0, len(xy) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = xy[i], xy[j]
        ab = b - a
        n = float(np.hypot(*ab))
        seg = xy[i + 1 : j]
        if n == 0:
            d = np.hypot(*(seg - a).T)
        else:
            d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / n
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k
            keep.add(m)
            stack += [(i, m), (m, j)]
    return sorted(keep)


def simplify(
    coords: Sequence[tuple[float, float]], tol_m: float, digits: int = 5
) -> list[tuple[float, float]]:
    ll = np.asarray(coords, dtype=float)
    keep = douglas_peucker(project(ll[:, 0], ll[:, 1]), tol_m)
    return [(round(float(ll[k, 0]), digits), round(float(ll[k, 1]), digits)) for k in keep]


def interpolate(arr: np.ndarray, along: float, ref: np.ndarray) -> np.ndarray:
    seglen = np.hypot(*np.diff(ref, axis=0).T)
    cum = np.r_[0, np.cumsum(seglen)]
    s = int(np.clip(np.searchsorted(cum, along) - 1, 0, len(seglen) - 1))
    t = 0.0 if seglen[s] == 0 else (along - cum[s]) / seglen[s]
    return arr[s] + t * (arr[s + 1] - arr[s])


def slice_line(ll: np.ndarray, xy: np.ndarray, a: float, b: float) -> np.ndarray:
    seglen = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.r_[0, np.cumsum(seglen)]
    inner = [ll[k] for k in range(len(ll)) if a < cum[k] < b]
    return np.array([interpolate(ll, a, xy), *inner, interpolate(ll, b, xy)])


def utm_to_lonlat(easting: float, northing: float, zone: int, south: bool = True) -> tuple[float, float]:
    """Inverse transverse Mercator on WGS84 (Snyder series, sub-metre over Chile)."""
    a, f, k0 = 6378137.0, 1 / 298.257223563, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x = easting - 500000.0
    y = northing - (10000000.0 if south else 0.0)
    mu = (y / k0) / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    s1, c1, t1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * s1**2)
    r1 = a * (1 - e2) / (1 - e2 * s1**2) ** 1.5
    cc, tt = ep2 * c1**2, t1**2
    d = x / (n1 * k0)
    lat = phi1 - (n1 * t1 / r1) * (
        d**2 / 2
        - (5 + 3 * tt + 10 * cc - 4 * cc**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * tt + 298 * cc + 45 * tt**2 - 252 * ep2 - 3 * cc**2) * d**6 / 720
    )
    lon = (
        d
        - (1 + 2 * tt + cc) * d**3 / 6
        + (5 - 2 * cc + 28 * tt - 3 * cc**2 + 8 * ep2 + 24 * tt**2) * d**5 / 120
    ) / c1
    return math.degrees(lon) + (zone * 6 - 183), math.degrees(lat)


class PointIndex:
    """Brute-force nearest-point index in projected metres (fine for a few thousand points)."""

    def __init__(self, lons: Sequence[float], lats: Sequence[float]) -> None:
        self.xy = project(np.asarray(lons, dtype=float), np.asarray(lats, dtype=float))

    def distances(self, lon: float, lat: float) -> np.ndarray:
        p = project(np.array([lon]), np.array([lat]))[0]
        return np.hypot(*(self.xy - p).T)

    def within(self, lon: float, lat: float, radius_m: float) -> list[tuple[int, float]]:
        d = self.distances(lon, lat)
        idx = np.where(d <= radius_m)[0]
        return sorted(((int(i), float(d[i])) for i in idx), key=lambda t: t[1])
