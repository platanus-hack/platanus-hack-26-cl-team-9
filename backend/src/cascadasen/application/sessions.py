"""Use cases for shared sessions (docs/stack.md 6.2): one JSON document per session holds an overlay
over the 188-bus network, pinned to one operating point, plus a sandbox cut state and the index of
its runs. Documents live in a `DocumentStore` (`sessions/<sid>.json`) and are written with
conditional writes, so several instances can serve the same session. Every change bumps the
document's `revision`; changes of the dataset (overlay edits, reset, cut, repair) also bump its
`dataset_revision`, which `If-Match` and the network view use, so run activity does not invalidate
them. Session runs reuse `RunManager` on a `SessionWorld` that pins the overlay
the run was created with (`sessions/<sid>/runs/<rid>.json`)."""

from __future__ import annotations

import copy
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cascadasen.application.run_experiment import RunCache, RunManager, RunNotFoundError, run_config
from cascadasen.application.simulation_service import theater_network_view
from cascadasen.application.theater_world import SessionWorld
from cascadasen.domain.cascade import overlay as ov
from cascadasen.domain.cascade.engine import run_cascade_workflow
from cascadasen.domain.ports import CommanderAdvisor, ConflictError, DocumentStore, Interpreter
from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.simulation.network import NetworkSpec
from cascadasen.domain.simulation.timeline import NOTICE
from cascadasen.domain.theater.cycle import RunInputError
from cascadasen.domain.theater.world import TheaterWorld

SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")
DEFAULT_POINT = "nov2026-1300"
MAX_RUNS_PER_SESSION = 20
WRITE_RETRIES = 3
CACHE_SIZE = 32
RUN_COMMANDS = ("state", "inject", "step", "action", "replay", "snapshots", "trace", "report", "after_action")
MUTATING = frozenset({"inject", "step", "action", "replay"})


class SessionNotFoundError(KeyError):
    pass


class PreconditionFailedError(RuntimeError):
    """The client's `If-Match` revision is not the current one (HTTP 412)."""


class SessionLimitError(ValueError):
    """A per-session limit was reached (HTTP 422)."""


class _Lru:
    def __init__(self, size: int) -> None:
        self.size, self._items, self._lock = size, OrderedDict(), threading.Lock()

    def get(self, key: Any) -> Any:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
            return None

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.size:
                self._items.popitem(last=False)

    def drop(self, match: Callable[[Any], bool]) -> None:
        with self._lock:
            for key in [k for k in self._items if match(k)]:
                del self._items[key]


class SessionService:
    def __init__(
        self,
        world: TheaterWorld,
        physics: Physics,
        store: DocumentStore,
        cache: RunCache,
        *,
        interpreter: Interpreter | None = None,
        advisor: CommanderAdvisor | None = None,
        spec: NetworkSpec | None = None,
        ttl_s: float = 86400,
        version: str = "dev",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.world, self.physics, self.store, self.cache = world, physics, store, cache
        self.interpreter, self.advisor, self.spec = interpreter, advisor, spec
        self.ttl_s, self.version, self.clock = ttl_s, version, clock
        self._docs = _Lru(256)  # sid -> (doc, etag): what SSE polls between store heads
        self._worlds = _Lru(CACHE_SIZE)  # (sid, dataset_revision) -> SessionWorld
        self._views = _Lru(CACHE_SIZE)  # (sid, dataset_revision) -> network view

    # --------------------------------------------------------------- store
    @staticmethod
    def _key(sid: str) -> str:
        if not isinstance(sid, str) or not SESSION_ID.match(sid):
            raise SessionNotFoundError(sid)
        return f"sessions/{sid}.json"

    def _now(self) -> str:
        return datetime.fromtimestamp(self.clock(), UTC).isoformat(timespec="seconds")

    def _fetch(self, sid: str) -> tuple[dict[str, Any], str]:
        found = self.store.get(self._key(sid))
        if found is None:
            self._docs.drop(lambda k: k == sid)
            raise SessionNotFoundError(sid)
        self._docs.put(sid, found)
        return found

    def _public(self, doc: dict[str, Any]) -> dict[str, Any]:
        updated = datetime.fromisoformat(doc["updated_at"]).timestamp()
        expires = datetime.fromtimestamp(updated + self.ttl_s, UTC).isoformat(timespec="seconds")
        return {**copy.deepcopy(doc), "share_path": f"/?sesion={doc['session_id']}", "expires_at": expires}

    def _world(self, doc: dict[str, Any]) -> SessionWorld:
        key = (doc["session_id"], doc["dataset_revision"])
        world = self._worlds.get(key)
        if world is None:
            world = SessionWorld(self.world, doc["point"], doc["overlay"], self.spec)
            self._worlds.put(key, world)
        return world

    def _base(self, point: str):
        net, op = self.world.load(point)
        return net.buses, op

    # ------------------------------------------------------------ document
    def create(self, point: str | None = None, label: str | None = None, by: str = "anon") -> dict[str, Any]:
        points = self.world.points()
        point = point or (DEFAULT_POINT if DEFAULT_POINT in points else points[0])
        if point not in points:
            raise RunInputError("point", "punto de operación desconocido", sorted(points))
        sid, now = secrets.token_urlsafe(16), self._now()
        doc = {
            "session_id": sid,
            "label": label,
            "point": point,
            "revision": 0,
            "dataset_revision": 0,
            "overlay": ov.empty_overlay(),
            "open_lines": [],
            "runs": {},
            "created_at": now,
            "updated_at": now,
            "last_op": {"op": "created", "ids": [], "by": by, "revision": 0, "dataset_revision": 0},
        }
        etag = self.store.put(self._key(sid), doc, if_none_match=True)
        self._docs.put(sid, (doc, etag))
        return self._public(doc)

    def get(self, sid: str) -> dict[str, Any]:
        return self._public(self._fetch(sid)[0])

    def delete(self, sid: str) -> None:
        doc, _ = self._fetch(sid)
        for rid in doc["runs"]:
            key = f"sessions/{sid}/runs/{rid}.json"
            self.store.delete(key)
            self.cache.evict(key)
        self.store.delete(self._key(sid))
        for lru in (self._docs, self._worlds, self._views):
            lru.drop(lambda k: k == sid or (isinstance(k, tuple) and k[0] == sid))

    def mutate(
        self,
        sid: str,
        fn: Callable[[dict[str, Any]], dict[str, Any] | None],
        op: str,
        ids: list[str] | None,
        by: str = "anon",
        if_revision: int | None = None,
        dataset: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Apply `fn` to a copy of the current document and write it conditionally, retrying on a
        concurrent write. `fn` edits the document in place and may return extra output; its `id`
        (or `ids`) becomes the operation's ids when `ids` is None. `dataset` marks a change of the
        dataset (bumps `dataset_revision`); `if_revision` is checked against `dataset_revision`."""
        for _ in range(WRITE_RETRIES + 1):
            doc, etag = self._fetch(sid)
            if if_revision is not None and doc["dataset_revision"] != if_revision:
                raise PreconditionFailedError(sid)
            new = copy.deepcopy(doc)
            out = fn(new) or {}
            new["revision"] = doc["revision"] + 1
            new["dataset_revision"] = doc["dataset_revision"] + int(dataset)
            op_ids = ids if ids is not None else out.get("ids") or ([out["id"]] if "id" in out else [])
            new["last_op"] = {
                "op": op,
                "ids": op_ids,
                "by": by,
                "revision": new["revision"],
                "dataset_revision": new["dataset_revision"],
            }
            new["updated_at"] = self._now()
            try:
                new_etag = self.store.put(self._key(sid), new, if_match=etag)
            except ConflictError:
                continue
            self._docs.put(sid, (new, new_etag))
            return new, out
        raise ConflictError(sid)

    def _edit(
        self,
        sid: str,
        change: Callable[[dict[str, Any], Any, Any], tuple[dict[str, Any], dict[str, Any]]],
        op: str,
        ids: list[str] | None,
        by: str,
        if_revision: int | None,
    ) -> dict[str, Any]:
        def fn(doc: dict[str, Any]) -> dict[str, Any]:
            net, point = self._base(doc["point"])
            doc["overlay"], out = change(doc["overlay"], net, point)
            applied = SessionWorld(self.world, doc["point"], doc["overlay"], self.spec).applied
            live = {ln.id for ln in applied.net.lines}
            doc["open_lines"] = [lid for lid in doc["open_lines"] if lid in live]
            return out

        doc, out = self.mutate(sid, fn, op, ids, by, if_revision, dataset=True)
        applied = self._world(doc).applied
        return {
            **out,
            "revision": doc["revision"],
            "dataset_revision": doc["dataset_revision"],
            "warnings": applied.warnings,
            "balance": applied.balance,
        }

    def add(
        self, sid: str, kind: str, fields: dict[str, Any], by: str = "anon", if_revision: int | None = None
    ) -> dict[str, Any]:
        def change(o, net, point):
            o, new_id = ov.add(o, kind, fields, net, point)
            return o, {"id": new_id}

        return self._edit(sid, change, f"{kind}_added", None, by, if_revision)

    def patch(
        self,
        sid: str,
        kind: str,
        element_id: str,
        fields: dict[str, Any],
        by: str = "anon",
        if_revision: int | None = None,
    ) -> dict[str, Any]:
        def change(o, net, point):
            return ov.patch(o, kind, element_id, fields, net, point), {"id": element_id}

        return self._edit(sid, change, f"{kind}_updated", [element_id], by, if_revision)

    def remove(
        self, sid: str, kind: str, element_id: str, by: str = "anon", if_revision: int | None = None
    ) -> dict[str, Any]:
        def change(o, net, point):
            return ov.remove(o, kind, element_id, net, point), {"id": element_id}

        return self._edit(sid, change, f"{kind}_removed", [element_id], by, if_revision)

    def reset(self, sid: str, by: str = "anon", if_revision: int | None = None) -> dict[str, Any]:
        return self._edit(sid, lambda o, net, point: (ov.empty_overlay(), {}), "reset", [], by, if_revision)

    # -------------------------------------------------------------- views
    def network_view(self, sid: str) -> dict[str, Any]:
        doc, _ = self._fetch(sid)
        key = (sid, doc["dataset_revision"])
        view = self._views.get(key)
        if view is None:
            view = self._network_view(doc)
            self._views.put(key, view)
        return {**copy.deepcopy(view), "revision": doc["revision"]}

    def _network_view(self, doc: dict[str, Any]) -> dict[str, Any]:
        world = self._world(doc)
        point, o = doc["point"], doc["overlay"]
        net, op = world.load(point)
        applied = world.applied
        base_net, _ = self._base(point)
        n = base_net.size
        removed = {r["id"] for r in o["buses"] if r.get("removed")}
        session_lines = {r["id"] for r in o["lines"]}
        overrides, line_overrides = o["bus_overrides"], o["line_overrides"]
        view = theater_network_view(net, op, point, [point])
        view["nodes"] = [nd for nd in view["nodes"] if nd["id"] not in removed]
        view["buses"] = {k: v for k, v in view["buses"].items() if k not in removed}
        for area in view["areas"]:
            area["buses"] = [b for b in area["buses"] if b not in removed]
        for nd in view["nodes"]:
            index = int(nd["id"][1:])
            session = index >= n
            nd["origin"] = "session" if session else "base"
            nd["overridden"] = not session and nd["id"] in overrides
            nd["in_service"] = (o["buses"][index - n] if session else overrides.get(nd["id"], {})).get(
                "in_service", True
            )
            nd["is_assumption"] = session or nd["overridden"]
            view["buses"][nd["id"]].update(origin=nd["origin"], is_assumption=nd["is_assumption"])
        for ln in view["lines"]:
            session = ln["id"] in session_lines
            ln["origin"] = "session" if session else "base"
            ln["overridden"] = not session and ln["id"] in line_overrides
            ln["is_assumption"] = session or ln["overridden"]
        live = {ln.id for ln in applied.net.lines}
        view["out_of_service"] = {
            "buses": [nd["id"] for nd in view["nodes"] if not nd["in_service"]],
            "lines": sorted({ln.id for ln in base_net.lines} - live)
            + [r["id"] for r in o["lines"] if r["id"] not in live],
        }
        view["loads"] = [{**r, "origin": "session", "is_assumption": True} for r in o["loads"]]
        view["generators"] = [{**r, "origin": "session", "is_assumption": True} for r in o["generators"]]
        view["warnings"], view["balance"] = applied.warnings, applied.balance
        view["baseline"] = self._baseline(net.buses, op)
        view["dataset_revision"], view["session_id"] = doc["dataset_revision"], doc["session_id"]
        return view

    @staticmethod
    def _baseline(net, op) -> dict[str, Any]:
        timeline = run_cascade_workflow(net, op, [])
        edges = timeline["frames"][0]["edges"]
        return {
            "max_loading": float(max((e["loading"] for e in edges.values()), default=0.0)),
            "overloaded": sorted(k for k, e in edges.items() if e["status"] == "overload"),
            "islands": timeline["summary"]["islands"],
            "load_shed_mw": timeline["summary"]["load_shed_mw"],
        }

    # ------------------------------------------------------------ sandbox
    def _timeline(self, doc: dict[str, Any]) -> dict[str, Any]:
        net, op = self._world(doc).load(doc["point"])
        return run_cascade_workflow(net.buses, op, sorted(doc["open_lines"]))

    def _check_lines(self, doc: dict[str, Any], lines: list[str]) -> None:
        live = {ln.id for ln in self._world(doc).applied.net.lines}
        unknown = sorted(set(lines) - live)
        if unknown:
            raise ov.OverlayError(
                "lines", f"Líneas desconocidas o fuera de servicio: {', '.join(unknown)}.", not_found=True
            )

    def _sandbox(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision": doc["revision"],
            "dataset_revision": doc["dataset_revision"],
            "open_lines": doc["open_lines"],
            "timeline": self._timeline(doc),
            "notice": NOTICE,
        }

    def cut(
        self, sid: str, lines: list[str], by: str = "anon", if_revision: int | None = None
    ) -> dict[str, Any]:
        if not 1 <= len(lines) <= ov.MAX_CUT_LINES:
            raise ov.OverlayError("lines", f"Corta entre 1 y {ov.MAX_CUT_LINES} líneas por llamada.")

        def fn(doc: dict[str, Any]) -> None:
            self._check_lines(doc, lines)
            doc["open_lines"] = sorted(set(doc["open_lines"]) | set(lines))

        doc, _ = self.mutate(sid, fn, "cut", sorted(lines), by, if_revision, dataset=True)
        return self._sandbox(doc)

    def repair(
        self,
        sid: str,
        lines: list[str] | None = None,
        all: bool = False,
        by: str = "anon",
        if_revision: int | None = None,
    ) -> dict[str, Any]:
        lines = list(lines or [])

        def fn(doc: dict[str, Any]) -> dict[str, Any]:
            repaired = list(doc["open_lines"]) if all else lines
            if not all:
                self._check_lines(doc, lines)
            doc["open_lines"] = [] if all else sorted(set(doc["open_lines"]) - set(lines))
            return {"ids": sorted(repaired)}

        doc, _ = self.mutate(sid, fn, "repair", None if all else sorted(lines), by, if_revision, dataset=True)
        return self._sandbox(doc)

    def state(self, sid: str) -> dict[str, Any]:
        return self._sandbox(self._fetch(sid)[0])

    # --------------------------------------------------------------- runs
    def runs(self, sid: str, doc: dict[str, Any] | None = None) -> RunManager:
        """The run manager of a session: new runs pin the current overlay; recorded runs are rebuilt
        on the overlay stored in their record."""
        doc = doc or self._fetch(sid)[0]
        return RunManager(
            self._world(doc),
            self.physics,
            interpreter=self.interpreter,
            advisor=self.advisor,
            store=self.store,
            prefix=f"sessions/{sid}/runs/",
            cache=self.cache,
            world_for=lambda rec: SessionWorld(
                self.world, rec["extra"]["point"], rec["extra"]["overlay"], self.spec
            ),
            extra={
                "session_id": sid,
                "point": doc["point"],
                "overlay": doc["overlay"],
                "dataset_revision": doc["dataset_revision"],
            },
            version=self.version,
            clock=self.clock,
        )

    def _register(self, sid: str, run: dict[str, Any], dataset_revision: int, by: str) -> int:
        rid = run["run_id"]

        def fn(doc: dict[str, Any]) -> None:
            if rid not in doc["runs"] and len(doc["runs"]) >= MAX_RUNS_PER_SESSION:
                raise SessionLimitError(f"Máximo {MAX_RUNS_PER_SESSION} corridas por sesión.")
            doc["runs"][rid] = {
                "created_at": self._now(),
                "dataset_revision": dataset_revision,
                "cycle": run["cycle"],
                "status": run["status"],
            }

        return self.mutate(sid, fn, "run_created", [rid], by)[0]["revision"]

    def _check_room(self, doc: dict[str, Any]) -> None:
        if len(doc["runs"]) >= MAX_RUNS_PER_SESSION:
            raise SessionLimitError(f"Máximo {MAX_RUNS_PER_SESSION} corridas por sesión.")

    def create_run(
        self, sid: str, data: dict[str, Any], auto_run: bool = False, by: str = "anon"
    ) -> dict[str, Any]:
        doc, _ = self._fetch(sid)
        self._check_room(doc)
        asked = data.get("point") or data.get("operating_point")
        if asked and asked != doc["point"]:
            raise RunInputError("point", "la sesión fija su punto de operación", [doc["point"]])
        config = run_config({**data, "point": doc["point"], "operating_point": doc["point"]})
        run = self.runs(sid, doc).create(config, auto_run)
        revision = self._register(sid, run, doc["dataset_revision"], by)
        return {**run, "session_revision": revision}

    def run_command(self, sid: str, rid: str, name: str, *args: Any, by: str = "anon", **kwargs: Any) -> Any:
        if name not in RUN_COMMANDS:
            raise ValueError(name)
        doc, _ = self._fetch(sid)
        if rid not in doc["runs"]:
            raise RunNotFoundError(rid)
        if name == "replay":
            self._check_room(doc)
        out = getattr(self.runs(sid, doc), name)(rid, *args, **kwargs)
        if name == "replay":
            info = doc["runs"][rid]
            out["session_revision"] = self._register(sid, out, info["dataset_revision"], by)
        elif name in MUTATING:
            run = out["run"]

            def fn(d: dict[str, Any]) -> None:
                if rid in d["runs"]:
                    d["runs"][rid].update(cycle=run["cycle"], status=run["status"])

            try:
                out["session_revision"] = self.mutate(sid, fn, "run_updated", [rid], by)[0]["revision"]
            except ConflictError:  # the step is persisted; only the index summary missed this write
                out["session_revision"] = self._fetch(sid)[0]["revision"]
        return out

    # ---------------------------------------------------------------- SSE
    def revision(self, sid: str) -> dict[str, Any]:
        """The cached document's revision and last operation (cheap; refreshed by `head`)."""
        found = self._docs.get(sid) or self._fetch(sid)
        doc = found[0]
        last = doc.get("last_op") or {}
        return {
            "revision": doc["revision"],
            "dataset_revision": doc["dataset_revision"],
            "op": last.get("op"),
            "ids": last.get("ids", []),
            "by": last.get("by"),
        }

    def head(self, sid: str) -> str:
        """The store etag of the document; reloads the cached copy when another instance wrote it."""
        etag = self.store.head(self._key(sid))
        if etag is None:
            self._docs.drop(lambda k: k == sid)
            raise SessionNotFoundError(sid)
        cached = self._docs.get(sid)
        if cached is None or cached[1] != etag:
            self._fetch(sid)
        return etag
