"""HTTP fetching with an on-disk cache of raw responses (data/raw/<source>/...).

A build first looks in the cache; `refresh=True` forces a new download. If a download fails and
a cached copy exists, the cached copy is used and a warning is logged, so a build still works
offline or when a public server is down during the demo.
"""

from __future__ import annotations

import http.cookiejar
import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    pass


class CachedHttp:
    def __init__(self, cache_dir: Path, timeout_s: float = 120.0, user_agent: str = "cascadasen") -> None:
        self.cache_dir = cache_dir
        self.timeout_s = timeout_s
        self.user_agent = user_agent
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def _request(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, **(headers or {})})
        last: Exception | None = None
        for attempt in range(4):
            try:
                with self.opener.open(req, timeout=self.timeout_s) as resp:
                    return resp.read()
            except OSError as exc:
                last = exc
                time.sleep(1.5 * 2**attempt)
        raise FetchError(f"GET {url} failed: {last}")

    def get_bytes(
        self, url: str, cache_name: str, refresh: bool = False, headers: dict | None = None
    ) -> bytes:
        path = self.cache_dir / cache_name
        if path.exists() and not refresh:
            return path.read_bytes()
        try:
            data = self._request(url, headers)
        except FetchError:
            if path.exists():
                log.warning("using cached %s after download failure", path)
                return path.read_bytes()
            raise
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    def get_json(self, url: str, cache_name: str, refresh: bool = False, params: dict | None = None) -> Any:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return json.loads(self.get_bytes(url, cache_name, refresh))

    def visit(self, url: str) -> None:
        """Open a page only to collect its cookies (e.g. a public SharePoint sharing link)."""
        self._request(url)

    def cached(self, cache_name: str) -> Path | None:
        path = self.cache_dir / cache_name
        return path if path.exists() else None
