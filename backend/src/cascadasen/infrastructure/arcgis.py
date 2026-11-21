"""Paged queries against ArcGIS REST MapServer / FeatureServer layers."""

from __future__ import annotations

import json
from typing import Any

from cascadasen.infrastructure.http import CachedHttp, FetchError


def query_layer(
    http: CachedHttp,
    layer_url: str,
    cache_name: str,
    refresh: bool = False,
    page_size: int = 1000,
    fmt: str = "geojson",
    **params: Any,
) -> list[dict[str, Any]]:
    """Return every feature of a layer, paging with resultOffset. Cached as one JSON file."""
    cached = http.cached(cache_name)
    if cached and not refresh:
        return json.loads(cached.read_text(encoding="utf-8"))["features"]
    features: list[dict[str, Any]] = []
    offset = 0
    try:
        while True:
            q = {
                "where": "1=1",
                "outFields": "*",
                "outSR": 4326,
                "f": fmt,
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": "OBJECTID",
                **params,
            }
            data = http.get_json(
                f"{layer_url}/query", f"_pages/{cache_name}.{offset}", refresh=True, params=q
            )
            if "error" in data:
                raise FetchError(f"{layer_url}: {data['error']}")
            batch = data.get("features", [])
            features += batch
            if len(batch) < page_size and not data.get("exceededTransferLimit"):
                break
            offset += len(batch)
    except FetchError:
        if cached:
            return json.loads(cached.read_text(encoding="utf-8"))["features"]
        raise
    path = http.cache_dir / cache_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8"
    )
    for page in (http.cache_dir / "_pages").glob(f"{cache_name}.*"):
        page.unlink()
    return features
