#!/usr/bin/env python3
"""Build docs/index/repo-index.json, a machine-readable map of the repository (schema: docs/index/README.md).

Standard library only. The one outside dependency is the route table, which comes from the real FastAPI app
(`cascadasen.api.app.create_app`), so run it with the backend environment:

    cd backend && uv run python ../scripts/build_index.py            # write the index
    cd backend && uv run python ../scripts/build_index.py --check    # exit 1 if the committed file is stale

Deterministic: no timestamps, no commit hashes, sorted output. It lists the files in the git index
(`git ls-files`), so `git add` a new file before regenerating. The index does not list itself.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "docs" / "index" / "repo-index.json"
INDEX_REL = "docs/index/repo-index.json"
REGEN = "cd backend && uv run python ../scripts/build_index.py"
SCHEMA_VERSION = 1
PKG_SRC = "backend/src/cascadasen/"
PURPOSE_MAX = 160

# extension (or file name) -> language of the files listed under `files`
LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".css": "css",
    ".html": "html",
    ".md": "markdown",
    ".sh": "shell",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".tf": "terraform",
    ".toml": "toml",
    "Dockerfile": "dockerfile",
}
# data and generated paths: never listed under `files`
DATA_DIRS = ("data/processed/", "data/scenarios/")
GENERATED_DIRS = ("web/public/cache/",)
TS_EXPORT = re.compile(
    r"^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?(function\*?|class|interface|type|enum|const|let)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
TS_KIND = {"function*": "function", "const": "const", "let": "const"}
TS_IMPORT = re.compile(r"""(?:from|import)\s+["'](\.[^"']*)["']""")
TS_TESTS = re.compile(r"^\s*(?:it|test)(?:\.\w+)?\(", re.MULTILINE)
DOTTED = re.compile(r"cascadasen(?:\.[A-Za-z_][A-Za-z_0-9]*)+")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True
    ).stdout.decode("utf-8")
    files = sorted(f for f in out.split("\0") if f and f != INDEX_REL)
    return [f for f in files if (ROOT / f).is_file()]


def language(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("Dockerfile") or name.endswith(".Dockerfile"):
        return "dockerfile"
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    return LANGUAGES.get(ext)


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return ("/tests/" in f"/{path}" and path.endswith(".py")) or bool(re.search(r"\.test\.tsx?$", name))


def kind(path: str, lang: str) -> str:
    if is_test(path):
        return "test"
    if lang == "markdown":
        return "doc"
    if lang == "shell" or (lang == "python" and (path.startswith("scripts/") or path.startswith("data/"))):
        return "script"
    if lang in {"python", "typescript", "css", "html"}:
        return "source"
    return "config"


def shorten(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= PURPOSE_MAX else text[: PURPOSE_MAX - 1].rstrip() + "…"


def comment_purpose(text: str) -> str:
    """First comment block of a non-Python file (after a shebang), without the comment markers."""
    lines = text.splitlines()
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    block: list[str] = []
    for line in lines:
        s = line.strip()
        if not s and not block:
            continue
        m = re.match(r"^(?:#|//|/\*+|\*)\s?(.*?)(?:\*/)?$", s)
        if not m:
            break
        piece = m.group(1).strip()
        if piece.startswith("@vitest-environment"):
            continue
        if not piece and block:
            break
        if piece:
            block.append(piece)
    return shorten(" ".join(block))


def md_headings(text: str) -> list[tuple[int, int, str]]:
    """(line, level, text) of every markdown heading outside code fences."""
    found, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if m:
                found.append((n, len(m.group(1)), m.group(2)))
    return found


def module_name(path: str) -> str | None:
    if not path.startswith(PKG_SRC) or not path.endswith(".py"):
        return None
    parts = path[len("backend/src/") : -3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def layer(path: str) -> str | None:
    if not path.startswith(PKG_SRC):
        return None
    rest = path[len(PKG_SRC) :].split("/")
    return rest[0] if len(rest) > 1 else "root"


def py_info(text: str) -> dict[str, Any]:
    """Docstring purpose, public symbols (top-level classes and functions, public methods) and test count."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"purpose": "", "symbols": [], "tests": 0}
    doc = ast.get_docstring(tree)
    symbols: list[dict[str, Any]] = []

    def add(name: str, kind_: str, node: ast.AST) -> None:
        sym: dict[str, Any] = {"name": name, "kind": kind_, "line": node.lineno}  # type: ignore[attr-defined]
        if not ast.get_docstring(node):  # type: ignore[arg-type]
            sym["undocumented"] = True
        symbols.append(sym)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            add(node.name, "function", node)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            add(node.name, "class", node)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_"):
                    add(f"{node.name}.{sub.name}", "method", sub)
    tests = sum(
        1
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
    )
    return {"purpose": shorten(doc.split("\n\n")[0]) if doc else "", "symbols": symbols, "tests": tests}


def ts_info(text: str) -> dict[str, Any]:
    symbols = [
        {
            "name": m.group(2),
            "kind": TS_KIND.get(m.group(1), m.group(1)),
            "line": text.count("\n", 0, m.start()) + 1,
        }
        for m in TS_EXPORT.finditer(text)
    ]
    return {"purpose": comment_purpose(text), "symbols": symbols, "tests": len(TS_TESTS.findall(text))}


def line_count(text: str) -> int:
    return len(text.splitlines())


def resolve_dotted(token: str, modules: dict[str, str]) -> str | None:
    """Path of the longest module that is a prefix of a dotted name found in a test."""
    parts = token.split(".")
    while parts:
        name = ".".join(parts)
        if name in modules:
            return modules[name]
        parts.pop()
    return None


def py_test_targets(text: str, modules: dict[str, str]) -> set[str]:
    """Source files a Python test imports or names (dotted names, also inside strings such as patch targets)."""
    tokens = set(DOTTED.findall(text))
    try:
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                tokens.update(f"{node.module}.{a.name}" for a in node.names)
    except SyntaxError:
        pass
    return {p for t in tokens if (p := resolve_dotted(t, modules))}


def ts_test_targets(path: str, text: str, known: set[str]) -> set[str]:
    base = Path(path).parent
    targets = set()
    for rel in TS_IMPORT.findall(text):
        stem = (base / rel).as_posix()
        stem = re.sub(r"/(?:\./)+", "/", stem)
        parts: list[str] = []
        for part in stem.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        stem = "/".join(parts)
        for cand in (stem, f"{stem}.ts", f"{stem}.tsx", f"{stem}/index.ts", f"{stem}/index.tsx"):
            if cand in known and not is_test(cand):
                targets.add(cand)
                break
    return targets


def build_files(paths: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    texts: dict[str, str] = {}
    skipped_ext: dict[str, int] = {}
    skipped_generated = {"files": 0, "bytes": 0}
    entries: list[dict[str, Any]] = []
    infos: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path.startswith(GENERATED_DIRS):
            skipped_generated["files"] += 1
            skipped_generated["bytes"] += (ROOT / path).stat().st_size
            continue
        if path.startswith(DATA_DIRS):
            continue
        lang = language(path)
        if lang is None:
            ext = Path(path).suffix or Path(path).name
            skipped_ext[ext] = skipped_ext.get(ext, 0) + 1
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        texts[path] = text
        entry: dict[str, Any] = {
            "path": path,
            "language": lang,
            "kind": kind(path, lang),
            "lines": line_count(text),
        }
        if lang == "python":
            info = py_info(text)
        elif lang == "typescript":
            info = ts_info(text)
        elif lang == "markdown":
            heads = md_headings(text)
            info = {
                "purpose": shorten(next((h[2] for h in heads if h[1] == 1), "")),
                "symbols": [],
                "tests": 0,
            }
        else:
            info = {"purpose": comment_purpose(text), "symbols": [], "tests": 0}
        infos[path] = info
        entry["purpose"] = info["purpose"]
        if (mod := module_name(path)) is not None:
            entry["module"] = mod
        if (lay := layer(path)) is not None:
            entry["layer"] = lay
        if entry["kind"] == "test":
            entry["test_count"] = info["tests"]
        elif info["symbols"]:
            entry["symbols"] = info["symbols"]
            undocumented = sum(1 for s in info["symbols"] if s.get("undocumented"))
            if undocumented:
                entry["undocumented"] = undocumented
        entries.append(entry)

    modules = {e["module"]: e["path"] for e in entries if "module" in e}
    known = set(texts)
    tested_by: dict[str, set[str]] = {}
    for e in entries:
        if e["kind"] != "test":
            continue
        if e["language"] == "python":
            targets = py_test_targets(texts[e["path"]], modules)
        else:
            targets = ts_test_targets(e["path"], texts[e["path"]], known)
        targets.discard(e["path"])
        e["covers"] = sorted(targets)
        for t in targets:
            tested_by.setdefault(t, set()).add(e["path"])
    for e in entries:
        if e["path"] in tested_by:
            e["tests"] = sorted(tested_by[e["path"]])
    skipped = {
        "generated": {"web/public/cache/": skipped_generated},
        "data_dirs": list(DATA_DIRS),
        "unindexed_extensions": dict(sorted(skipped_ext.items())),
    }
    return entries, skipped


def build_routes(app: Any = None) -> list[dict[str, Any]]:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    import inspect

    from fastapi.routing import iter_route_contexts

    from cascadasen.api.agent_openapi import agent_openapi
    from cascadasen.api.app import create_app

    app = app or create_app()
    full = app.openapi()["paths"]
    agent = agent_openapi(app)["paths"]
    rows = []
    for r in iter_route_contexts(app.routes):
        if not r.methods or r.endpoint is None:
            continue
        fn = inspect.unwrap(r.endpoint)
        code = getattr(fn, "__code__", None)
        try:
            src = Path(inspect.getsourcefile(fn) or "").resolve().relative_to(ROOT).as_posix()
        except ValueError:
            src = ""
        if not src.startswith(
            "backend/src/"
        ):  # FastAPI's own /docs and /openapi.json: path depends on the venv
            src = ""
        for method in sorted(r.methods):
            op = full.get(r.path, {}).get(method.lower())
            rows.append(
                {
                    "method": method,
                    "path": r.path,
                    "operation_id": op["operationId"] if op else None,
                    "summary": (op or {}).get("summary"),
                    "tags": (op or {}).get("tags", []),
                    "in_agent_spec": method.lower() in agent.get(r.path, {}),
                    "in_openapi": op is not None,
                    "handler": f"{src}:{code.co_firstlineno}" if src and code else None,
                }
            )
    return sorted(rows, key=lambda x: (x["path"], x["method"]))


def build_docs(paths: list[str]) -> list[dict[str, Any]]:
    docs = []
    for path in paths:
        if not path.endswith(".md"):
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        heads = md_headings(text)
        title = next((h[2] for h in heads if h[1] == 1), "")
        if path == "CHANGELOG.md":  # one heading per commit: listed under `changelog`
            heads = [h for h in heads if h[1] == 1]
        docs.append(
            {
                "path": path,
                "title": title,
                "lines": line_count(text),
                "headings": [{"line": n, "level": lv, "text": t} for n, lv, t in heads if lv <= 3],
            }
        )
    return docs


def build_data_files(paths: list[str]) -> list[dict[str, Any]]:
    return [{"path": p, "bytes": (ROOT / p).stat().st_size} for p in paths if p.startswith(DATA_DIRS)]


def build_changelog() -> list[dict[str, Any]]:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return [{"line": n, "heading": t} for n, lv, t in md_headings(text) if lv == 2]


def build_index(app: Any = None) -> dict[str, Any]:
    paths = tracked_files()
    files, skipped = build_files(paths)
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "scripts/build_index.py",
        "regenerate": REGEN,
        "schema": "docs/index/README.md",
        "counts": {
            "files": len(files),
            "by_kind": dict(sorted(_count(e["kind"] for e in files).items())),
            "by_language": dict(sorted(_count(e["language"] for e in files).items())),
            "undocumented_public_symbols": sum(e.get("undocumented", 0) for e in files),
        },
        "skipped": skipped,
        "files": files,
        "routes": build_routes(app),
        "docs": build_docs(paths),
        "data_files": build_data_files(paths),
        "changelog": build_changelog(),
    }


def _count(items: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def dumps(index: dict[str, Any]) -> str:
    """One line per array item (diff-friendly, grep-friendly); keys sorted."""

    def one(value: Any) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(", ", ": "))

    lines = []
    for key in index:
        value = index[key]
        if isinstance(value, list):
            body = ",\n".join("    " + one(v) for v in value)
            lines.append(f"  {json.dumps(key)}: [\n{body}\n  ]" if value else f"  {json.dumps(key)}: []")
        else:
            lines.append(f"  {json.dumps(key)}: {one(value)}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


def main(argv: list[str]) -> int:
    text = dumps(build_index())
    if "--check" in argv:
        current = INDEX_FILE.read_text(encoding="utf-8") if INDEX_FILE.exists() else ""
        if current != text:
            print(f"{INDEX_REL} is stale; run `{REGEN}`", file=sys.stderr)
            return 1
        return 0
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(text, encoding="utf-8")
    print(f"wrote {INDEX_FILE} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
