# Repository index

`repo-index.json` is a generated, machine-readable map of the repository. An agent can find a file, a public symbol, an API route, a doc section or a test with one `jq` query instead of reading the tree. It is built by `scripts/build_index.py` (Python standard library; the route table imports the real FastAPI app).

## Regenerate

```bash
cd backend && uv run python ../scripts/build_index.py           # writes docs/index/repo-index.json
cd backend && uv run python ../scripts/build_index.py --check   # exit 1 if the committed file is stale
```

- `tests/integration/test_repo_index.py` fails while the committed file differs from the generated one (the same rule as `tests/integration/test_agent_openapi.py`). It runs in its own job `repo-index` of `.github/workflows/checks.yml`, which is informational (`continue-on-error`): the index holds line numbers and CHANGELOG headings, so it is stale after almost any commit and must not block a deploy.
- Regenerate before each commit that adds, removes or edits a source, doc or test file, a route, or a CHANGELOG entry. Line counts and symbol line numbers move with every edit.
- The builder lists `git ls-files` (the git index), so run `git add` on a new file before regenerating. After `git add -A` and a regeneration, committing does not change the index: the file does not list itself and holds no timestamp or commit hash.
- Output is deterministic: sorted paths, one JSON object per line, no timestamps. Two runs give byte-identical files.
- Size: about 290 KB (the test asserts < 1 MB).

## What it leaves out

- `web/public/cache/**` (the generated cascade cache): only a count and a byte total, under `skipped.generated`.
- `data/processed/**` and `data/scenarios/**`: listed with sizes under `data_files`, never opened.
- Files with other extensions (`.json`, `.geojson`, images, `.lock`, ignore files, `.jsonc`): counted per extension under `skipped.unindexed_extensions`.
- Files that are not in git (`node_modules`, `.venv`, `data/raw`).
- Bodies of any file. Symbols carry a name, a kind and a line, not a signature or a docstring.

## Schema (`schema_version` 1)

Top-level keys, in file order:

| Key | Content |
|---|---|
| `changelog` | One row per `CHANGELOG.md` entry, newest first: `{line, heading}`. |
| `counts` | `files`, `by_kind`, `by_language`, `undocumented_public_symbols`. |
| `data_files` | `{path, bytes}` for tracked files in `data/processed/` and `data/scenarios/`. |
| `docs` | One row per tracked `.md` file: `{path, title, lines, headings: [{line, level, text}]}`. Levels 1-3 only. `CHANGELOG.md` lists only its title (its entries are under `changelog`). |
| `files` | One row per indexed source, test, doc, script and config file (below). |
| `generator`, `regenerate`, `schema`, `schema_version` | Where the file comes from and how to rebuild it. |
| `routes` | The API route table (below). |
| `skipped` | What `files` leaves out (section above). |

### `files[]`

| Field | Meaning |
|---|---|
| `path` | Repo-relative path. |
| `language` | `python`, `typescript` (`.ts` and `.tsx`), `markdown`, `css`, `html`, `shell`, `yaml`, `terraform`, `toml`, `dockerfile`. |
| `kind` | `source`, `test`, `doc`, `script` (shell files, and Python under `scripts/` and `data/`), `config` (yaml, terraform, toml, Dockerfile). |
| `lines` | Line count. |
| `purpose` | Python: first paragraph of the module docstring. Markdown: first `#` heading. Other files: first comment block. Cut at 160 characters. Empty when the file has none. |
| `module`, `layer` | Only for `backend/src/cascadasen/**`. `module` is the dotted name. `layer` is `api`, `application`, `domain`, `infrastructure`, `mcp` or `root` (`cli.py`, `sim_fixtures.py`, the package `__init__.py`). The layering rule is `docs/adr/0005-hexagonal-layering.md`. |
| `symbols` | Public symbols, in source order: `{name, kind, line}`. Python: top-level classes and functions, and the public methods of public classes (`kind` `method`, `name` `Class.method`). TypeScript: `export`ed function, class, interface, type, enum and const. A Python symbol with no docstring has `"undocumented": true`. TypeScript symbols never carry that flag. |
| `undocumented` | Number of Python symbols in the file with `"undocumented": true`. Absent when 0. |
| `tests` | For a non-test file: the test files that import or name it. Python tests are matched on any `cascadasen.<module>` dotted name in the test, including strings such as patch targets (the longest module prefix wins). TypeScript tests are matched on their relative imports. |
| `test_count`, `covers` | Only for test files. `test_count` is the number of `test_*` functions (Python) or `it(`/`test(` calls (TypeScript). `covers` is the reverse of `tests`. |

The `tests` match is a text match, not coverage. A test that only names a module in a string still counts.

### `routes[]`

One row per method and path of the app that `cascadasen.api.app.create_app()` builds.

| Field | Meaning |
|---|---|
| `method`, `path` | HTTP method and path. |
| `operation_id`, `summary`, `tags` | From the app's full OpenAPI. `null` and `[]` for routes with `include_in_schema=False`. |
| `in_openapi` | `true` when the route is in the app's full OpenAPI. |
| `in_agent_spec` | `true` when the operation is in `docs/openapi/agents.openapi.json` (routes marked `AGENT`, `docs/openapi.md`). |
| `handler` | `path:line` of the handler function (the first decorator line). `null` for FastAPI's own `/docs` and `/openapi.json`. |

## Queries (`jq`)

Run from the repository root, with `I=docs/index/repo-index.json`.

```bash
# Where is a symbol defined?
jq -r '.files[] | select(.symbols) | . as $f | .symbols[] | select(.name == "create_app") | "\($f.path):\(.line)"' $I

# What is a file for, and which tests cover it?
jq '.files[] | select(.path == "backend/src/cascadasen/domain/cascade/engine.py") | {purpose, lines, tests}' $I

# Which source files does a test file cover?
jq -r '.files[] | select(.path == "backend/tests/integration/test_agent_openapi.py") | .covers[]' $I

# All files of one layer
jq -r '.files[] | select(.layer == "domain") | "\(.lines)\t\(.path)"' $I | sort -rn | head

# Largest source files
jq -r '.files[] | select(.kind == "source") | "\(.lines)\t\(.path)"' $I | sort -rn | head

# The agent API routes with their handlers
jq -r '.routes[] | select(.in_agent_spec) | "\(.method) \(.path)\t\(.operation_id)\t\(.handler)"' $I

# Routes outside the agent spec that are in the full OpenAPI
jq -r '.routes[] | select(.in_openapi and (.in_agent_spec | not)) | "\(.method) \(.path)"' $I

# Which doc covers a topic? (headings contain the word)
jq -r '.docs[] | . as $d | .headings[] | select(.text | test("cascade"; "i")) | "\($d.path):\(.line)  \(.text)"' $I

# Public Python symbols without a docstring, worst files first
jq -r '.files[] | select(.undocumented) | "\(.undocumented)\t\(.path)"' $I | sort -rn | head

# Data files by size
jq -r '.data_files[] | "\(.bytes)\t\(.path)"' $I | sort -rn | head

# The last five CHANGELOG entries
jq -r '.changelog[:5][] | "CHANGELOG.md:\(.line)  \(.heading)"' $I
```

Open the file at the reported line (`sed -n '36,60p' path`) instead of reading the whole file.
