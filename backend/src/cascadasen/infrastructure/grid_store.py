"""GridStore adapters (domain/ports.py): the grid documents on disk or under a prefix of an S3 bucket."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cascadasen.domain.ports import ConflictError


class LocalGridStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.split("/") or "\\" in key:
            raise ValueError(f"clave inválida: {key!r}")
        return self.root / key

    def read(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as f:
                f.write(data)
        except FileExistsError as exc:
            raise ConflictError(f"ya existe {key}") from exc

    def keys(self) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())


class S3GridStore:
    def __init__(
        self,
        bucket: str,
        prefix: str,
        region: str | None = None,
        profile: str | None = None,
        client: Any = None,
    ) -> None:
        self.bucket, self.prefix = bucket, prefix.strip("/")
        if client is None:
            import boto3

            client = boto3.Session(profile_name=profile, region_name=region).client("s3")
        self.client = client

    def _key(self, key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"clave inválida: {key!r}")
        return f"{self.prefix}/{key}"

    def read(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise

    def write(self, key: str, data: bytes) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(key),
                Body=data,
                ContentType="application/json",
                IfNoneMatch="*",  # never overwrite
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "PreconditionFailed",
                "ConditionalRequestConflict",
            ):
                raise ConflictError(f"ya existe {key}") from exc
            raise

    def keys(self) -> list[str]:
        out: list[str] = []
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=self.prefix + "/"
        )
        for page in pages:
            out += [o["Key"][len(self.prefix) + 1 :] for o in page.get("Contents", [])]
        return sorted(out)
