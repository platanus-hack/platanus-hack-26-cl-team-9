"""Agent-only OpenAPI spec (docs/openapi.md): marked routes only, documented, and in sync with the
committed docs/openapi/agents.openapi.json."""

import json
import re

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from cascadasen.api.agent_openapi import SPEC_FILE, SPEC_URL, agent_openapi
from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService

METHODS = {"get", "post", "put", "patch", "delete"}
REGEN = "cd backend && uv run python -m cascadasen.api.agent_openapi"


@pytest.fixture
def app(toy_snapshot):
    return create_app(service=GridQueryService(toy_snapshot))


def operations(spec):
    return [(m, p, op) for p, ops in spec["paths"].items() for m, op in ops.items() if m in METHODS]


def test_spec_holds_exactly_the_marked_routes(app):
    marked = {
        (m.lower(), r.path)
        for r in iter_route_contexts(app.routes)
        if (getattr(r, "openapi_extra", None) or {}).get("x-sub50-agent")
        for m in r.methods
    }
    ops = operations(agent_openapi(app))
    assert {(m, p) for m, p, _ in ops} == marked
    assert all(op.get("x-sub50-agent") is True for _, _, op in ops)
    paths = set(agent_openapi(app)["paths"])
    assert {"/api/v1/sim/catalog", "/api/v1/sim/runs", "/api/v1/sim/runs/{run_id}/step"} <= paths
    assert not paths & {"/api/v1/simulate", "/api/v1/nodes", "/api/v1/health", "/api/v1/sim/campaigns"}


def test_every_operation_is_documented(app):
    spec = agent_openapi(app)
    ids = [op["operationId"] for _, _, op in operations(spec)]
    assert len(ids) == len(set(ids))
    for method, path, op in operations(spec):
        where = f"{method.upper()} {path}"
        assert re.fullmatch(r"[a-z]+(_[a-z0-9]+)+", op["operationId"]), where
        assert op.get("summary") and op.get("description"), where
        assert op.get("tags"), where
        for param in op.get("parameters", []):
            assert param.get("description") and param["schema"].get("examples"), (where, param["name"])
        for code, resp in op["responses"].items():
            if code[0] in "45":
                assert resp["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/ErrorResponse"
                }, (where, code)


def test_request_bodies_describe_every_field(app):
    schemas = agent_openapi(app)["components"]["schemas"]
    refs = [  # optional bodies (POST /sessions) are anyOf [$ref, null]
        ref
        for _, _, op in operations(agent_openapi(app))
        if "requestBody" in op
        for ref in re.findall(
            r'"\$ref": "([^"]+)"', json.dumps(op["requestBody"]["content"]["application/json"]["schema"])
        )
    ]
    seen = set()
    while refs:
        name = refs.pop().rsplit("/", 1)[-1]
        if name in seen:
            continue
        seen.add(name)
        for field, prop in schemas[name].get("properties", {}).items():
            assert prop.get("description"), f"{name}.{field}"
            refs += re.findall(r'"\$ref": "([^"]+)"', json.dumps(prop))
    assert {"RunCreate", "EventIn", "AdversaryIn"} <= seen


def test_committed_spec_matches_the_app(app):
    committed = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    assert committed == agent_openapi(app), f"docs/openapi/agents.openapi.json is stale; run `{REGEN}`"


def test_agent_spec_is_served_and_full_spec_unchanged(app):
    client = TestClient(app)
    served = client.get(SPEC_URL)
    assert served.status_code == 200 and served.json() == agent_openapi(app)
    assert client.get("/api/v1/agents/docs").status_code == 200
    full = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/nodes" in full and "/api/v1/simulate" in full and SPEC_URL not in full
