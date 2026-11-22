"""Repository index (docs/index/README.md): the committed docs/index/repo-index.json must equal the one
`scripts/build_index.py` generates now, like the agent OpenAPI spec. Fails when a file, a public symbol, a
route or a CHANGELOG heading changed without regenerating."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build_index.py"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="the index lists `git ls-files`; needs git and a checkout",
)


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("build_index", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_index"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated(builder):
    return builder.dumps(builder.build_index())


def test_committed_index_matches_the_repository(builder, generated):
    committed = builder.INDEX_FILE.read_text(encoding="utf-8")
    if committed != generated:
        old, new = json.loads(committed), json.loads(generated)
        stale = sorted(k for k in new if old.get(k) != new[k])
        pytest.fail(f"{builder.INDEX_REL} is stale (sections: {', '.join(stale)}); run `{builder.REGEN}`")


def test_generation_is_deterministic_and_small(builder, generated):
    assert builder.dumps(builder.build_index()) == generated
    assert len(generated.encode("utf-8")) < 1_000_000
    index = json.loads(generated)
    assert builder.INDEX_REL not in {f["path"] for f in index["files"]}  # the index does not list itself
    assert not any("web/public/cache/" in f["path"] for f in index["files"])


def test_index_has_the_documented_sections(generated):
    index = json.loads(generated)
    assert {"files", "routes", "docs", "data_files", "changelog", "counts", "skipped"} <= set(index)
    app = next(f for f in index["files"] if f["path"] == "backend/src/cascadasen/api/app.py")
    assert app["layer"] == "api" and app["module"] == "cascadasen.api.app"
    assert any(s["name"] == "create_app" for s in app["symbols"])
    assert "backend/tests/integration/test_agent_openapi.py" in app["tests"]
    agent_routes = [r for r in index["routes"] if r["in_agent_spec"]]
    assert agent_routes and all(r["operation_id"] and r["summary"] for r in agent_routes)
