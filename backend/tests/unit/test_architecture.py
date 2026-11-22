"""Layering rules of the hexagonal architecture (docs/architecture.md section 2, docs/adr/0005).

The test parses every module under `src/cascadasen` with `ast` and builds the import graph. It does not
import the package. A layer is the second component of the dotted module name (`cascadasen.domain.x` is
`domain`).
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = "cascadasen"

# application modules that import infrastructure today. They are composition-root entry points (CLI
# `main()` functions that build the settings and stores) and `run_experiment`'s default document store.
# Moving them behind ports is a larger refactor (review B-08), so new leaks fail the test but these stay.
# `api` imports `mcp` in 4 places (the assistant reuses the MCP tool functions). That edge is not asserted.
KNOWN_EXCEPTIONS = {
    ("cascadasen.application.build_regional", "cascadasen.infrastructure.container"),
    ("cascadasen.application.build_regional", "cascadasen.infrastructure.settings"),
    ("cascadasen.application.grid_health", "cascadasen.infrastructure.settings"),
    ("cascadasen.application.grids", "cascadasen.infrastructure.grid_store"),
    ("cascadasen.application.grids", "cascadasen.infrastructure.settings"),
    ("cascadasen.application.run_experiment", "cascadasen.infrastructure.document_store"),
}


def _mod_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _layer(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else "(root)"


def _resolve(path: Path, node: ast.Import | ast.ImportFrom) -> list[str]:
    """Dotted names an import statement may refer to (the module and, for `from`, each imported name)."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if node.level:
        base = _mod_name(path).split(".")
        if path.name != "__init__.py":
            base = base[:-1]
        base = base[: len(base) - (node.level - 1)]
        module = ".".join(base + ([node.module] if node.module else []))
    else:
        module = node.module or ""
    return [module] + [f"{module}.{a.name}" for a in node.names]


def _import_graph() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(all imports, top-level imports only) as {importing module: {imported modules of the package}}."""
    files = sorted(SRC.rglob("*.py"))
    known = {_mod_name(f) for f in files}
    everything: dict[str, set[str]] = defaultdict(set)
    top_level: dict[str, set[str]] = defaultdict(set)
    for path in files:
        source = _mod_name(path)
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            for name in _resolve(path, node):
                if not (name == PKG or name.startswith(PKG + ".")):
                    continue
                target = name
                while target and target not in known:  # `from pkg import name` may name an attribute
                    target = target.rpartition(".")[0]
                if not target or target == source:
                    continue
                everything[source].add(target)
                if node.col_offset == 0:  # function-local imports are indented
                    top_level[source].add(target)
    return everything, top_level


def _offenders(graph: dict[str, set[str]], importers: set[str], forbidden: set[str]) -> set[tuple[str, str]]:
    return {
        (src, dst)
        for src, targets in graph.items()
        if _layer(src) in importers
        for dst in targets
        if _layer(dst) in forbidden
    }


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []
    counter = [0]
    sys.setrecursionlimit(10000)

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            component = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            if len(component) > 1:
                found.append(sorted(component))

    for v in list(graph):
        if v not in index:
            visit(v)
    return found


ALL_IMPORTS, TOP_LEVEL_IMPORTS = _import_graph()


def test_domain_imports_no_outer_layer() -> None:
    outer = {"api", "application", "infrastructure", "mcp", "cli", "sim_fixtures"}
    assert _offenders(ALL_IMPORTS, {"domain"}, outer) == set()


def test_application_does_not_import_the_delivery_layers() -> None:
    assert _offenders(ALL_IMPORTS, {"application"}, {"api", "mcp"}) == set()


def test_infrastructure_does_not_import_the_delivery_layers() -> None:
    assert _offenders(ALL_IMPORTS, {"infrastructure"}, {"api", "mcp"}) == set()


def test_application_imports_infrastructure_only_in_the_known_modules() -> None:
    assert _offenders(ALL_IMPORTS, {"application"}, {"infrastructure"}) == KNOWN_EXCEPTIONS


def test_no_import_cycles_among_modules_with_top_level_imports() -> None:
    assert _cycles(TOP_LEVEL_IMPORTS) == []
