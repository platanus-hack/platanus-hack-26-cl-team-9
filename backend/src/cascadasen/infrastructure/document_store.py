"""DocumentStore adapters (domain/ports.py): JSON documents by key with conditional writes.

- `MemoryDocumentStore`: one process, tests and the default when nothing is configured.
- `FileDocumentStore`: one machine (docker compose), files under `data/sessions/`.
- `S3DocumentStore`: several instances; S3 conditional writes (`IfMatch` / `IfNoneMatch`).

Memory and file stores treat entries older than `ttl_s` since their last write as missing; S3 relies
on the bucket lifecycle rule instead. Every put renews the entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cascadasen.domain.ports import ConflictError


def _encode(doc: dict) -> bytes:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()


def _etag(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check(current: str | None, if_match: str | None, if_none_match: bool) -> None:
    if if_none_match and current is not None:
        raise ConflictError("el documento ya existe")
    if if_match is not None and current != if_match:
        raise ConflictError("el documento cambió")


class MemoryDocumentStore:
    def __init__(self, ttl_s: float | None = None, clock: Callable[[], float] = time.time) -> None:
        self.ttl_s, self.clock = ttl_s, clock
        self._docs: dict[str, tuple[bytes, str, float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str) -> tuple[bytes, str, float] | None:
        entry = self._docs.get(key)
        if entry and self.ttl_s is not None and self.clock() - entry[2] > self.ttl_s:
            return None
        return entry

    def get(self, key: str) -> tuple[dict, str] | None:
        entry = self._live(key)
        return (json.loads(entry[0]), entry[1]) if entry else None

    def put(self, key: str, doc: dict, *, if_match: str | None = None, if_none_match: bool = False) -> str:
        data = _encode(doc)
        with self._lock:
            now = self.clock()
            if self.ttl_s is not None:
                for k in [k for k, (_, _, at) in self._docs.items() if now - at > self.ttl_s]:
                    del self._docs[k]
            entry = self._docs.get(key)
            _check(entry[1] if entry else None, if_match, if_none_match)
            etag = _etag(data)
            self._docs[key] = (data, etag, now)
            return etag

    def head(self, key: str) -> str | None:
        entry = self._live(key)
        return entry[1] if entry else None

    def delete(self, key: str) -> None:
        with self._lock:
            self._docs.pop(key, None)


class FileDocumentStore:
    def __init__(
        self, root: Path | str, ttl_s: float | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self.root, self.ttl_s, self.clock = Path(root), ttl_s, clock
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.split("/") or "\\" in key:
            raise ValueError(f"clave inválida: {key!r}")
        return self.root / key

    def _read(self, path: Path) -> bytes | None:
        try:
            if self.ttl_s is not None and self.clock() - path.stat().st_mtime > self.ttl_s:
                return None
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def get(self, key: str) -> tuple[dict, str] | None:
        data = self._read(self._path(key))
        return (json.loads(data), _etag(data)) if data is not None else None

    def put(self, key: str, doc: dict, *, if_match: str | None = None, if_none_match: bool = False) -> str:
        path, data = self._path(key), _encode(doc)
        with self._lock:
            current = self._read(path)
            _check(_etag(current) if current is not None else None, if_match, if_none_match)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_bytes(data)
            now = self.clock()
            os.utime(tmp, (now, now))  # the TTL is measured with the store's clock
            os.replace(tmp, path)
            return _etag(data)

    def head(self, key: str) -> str | None:
        data = self._read(self._path(key))
        return _etag(data) if data is not None else None

    def delete(self, key: str) -> None:
        with self._lock:
            self._path(key).unlink(missing_ok=True)


_CONFLICT_CODES = {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}
_MISSING_CODES = {"NoSuchKey", "NotFound", "404"}


class S3DocumentStore:
    def __init__(
        self, bucket: str, region: str | None = None, profile: str | None = None, client: Any = None
    ) -> None:
        self.bucket = bucket
        if client is None:
            import boto3

            client = boto3.Session(profile_name=profile, region_name=region).client("s3")
        self.client = client

    @staticmethod
    def _code(exc: Exception) -> str:
        resp = getattr(exc, "response", None) or {}
        code = str((resp.get("Error") or {}).get("Code", ""))
        status = str((resp.get("ResponseMetadata") or {}).get("HTTPStatusCode", ""))
        return code if code in _CONFLICT_CODES | _MISSING_CODES else status

    def get(self, key: str) -> tuple[dict, str] | None:
        from botocore.exceptions import ClientError

        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._code(exc) in _MISSING_CODES:
                return None
            raise
        return json.loads(obj["Body"].read()), obj["ETag"]

    def put(self, key: str, doc: dict, *, if_match: str | None = None, if_none_match: bool = False) -> str:
        from botocore.exceptions import ClientError

        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": _encode(doc),
            "ContentType": "application/json",
        }
        if if_match is not None:
            kwargs["IfMatch"] = if_match
        if if_none_match:
            kwargs["IfNoneMatch"] = "*"
        try:
            return self.client.put_object(**kwargs)["ETag"]
        except ClientError as exc:
            if self._code(exc) in _CONFLICT_CODES:
                raise ConflictError("el documento cambió") from exc
            if if_match is not None and self._code(exc) in _MISSING_CODES:
                raise ConflictError("el documento ya no existe") from exc
            raise

    def head(self, key: str) -> str | None:
        from botocore.exceptions import ClientError

        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)["ETag"]
        except ClientError as exc:
            if self._code(exc) in _MISSING_CODES:
                return None
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
