#!/usr/bin/env bash
# Lint the given files with the right tool for each file type.
#
# Usage: scripts/lint.sh --fix|--check FILE...
#   --fix    apply safe fixes and formatting, then report what is left
#   --check  report only, change nothing (used by the git pre-commit hook and CI)
#
# Python      -> ruff check + ruff format (config: backend/pyproject.toml)
# web/*.ts(x) -> tsc --noEmit on the whole web project (once per run), when web/node_modules is installed
#                (eslint and prettier run too if web/node_modules/.bin has them; they are not dependencies today)
# Other files -> skipped
#
# Exit code: 0 when clean (or nothing to lint), 1 when problems remain.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-}"
if [[ "$mode" != "--fix" && "$mode" != "--check" ]]; then
  echo "usage: scripts/lint.sh --fix|--check FILE..." >&2
  exit 64
fi
shift

py_files=()
fe_files=()
for f in "$@"; do
  [[ -f "$f" ]] || continue                      # deleted or not a file
  abs="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
  case "$abs" in
    "$ROOT"/*/.venv/* | "$ROOT"/node_modules/* | "$ROOT"/*/node_modules/*) continue ;;
    *.py) py_files+=("$abs") ;;
    "$ROOT"/web/*.ts | "$ROOT"/web/*.tsx | "$ROOT"/web/*.js | "$ROOT"/web/*.jsx | \
    "$ROOT"/web/*.mjs | "$ROOT"/web/*.cjs | "$ROOT"/web/*.css | "$ROOT"/web/*.json)
      fe_files+=("$abs") ;;
  esac
done

status=0

# --- Python: ruff -----------------------------------------------------------
if ((${#py_files[@]})); then
  # Run from backend/ so files outside it (data/scripts) use the same ruff config (backend/pyproject.toml).
  cd "$ROOT/backend" || exit 1
  if [[ -x "$ROOT/backend/.venv/bin/ruff" ]]; then
    RUFF=("$ROOT/backend/.venv/bin/ruff")
  elif command -v uv >/dev/null 2>&1; then
    RUFF=(uv run --quiet --project "$ROOT/backend" ruff)
  elif command -v ruff >/dev/null 2>&1; then
    RUFF=(ruff)
  else
    echo "lint: ruff not found. Run 'cd backend && uv sync'." >&2
    exit 1
  fi
  if [[ "$mode" == "--fix" ]]; then
    "${RUFF[@]}" check --fix --quiet "${py_files[@]}" >/dev/null 2>&1
    "${RUFF[@]}" format --quiet "${py_files[@]}" || status=1
    "${RUFF[@]}" check --quiet "${py_files[@]}" || status=1
  else
    "${RUFF[@]}" check --quiet "${py_files[@]}" || status=1
    "${RUFF[@]}" format --check --quiet "${py_files[@]}" || status=1
  fi
fi

# --- Web: tsc + eslint + prettier (each only when installed) -----------------
if ((${#fe_files[@]})); then
  bin="$ROOT/web/node_modules/.bin"
  js_files=()
  ts_files=()
  for f in "${fe_files[@]}"; do
    case "$f" in
      *.css | *.json) ;;
      *) js_files+=("$f") ;;
    esac
    case "$f" in *.ts | *.tsx) ts_files+=("$f") ;; esac
  done
  # tsc checks the whole project (tsconfig.json), so it runs once; it has nothing to fix.
  if [[ -x "$bin/tsc" ]] && ((${#ts_files[@]})); then
    (cd "$ROOT/web" && "$bin/tsc" --noEmit) || status=1
  fi
  if [[ -x "$bin/eslint" ]] && ((${#js_files[@]})); then
    if [[ "$mode" == "--fix" ]]; then
      (cd "$ROOT/web" && "$bin/eslint" --fix "${js_files[@]}") || status=1
    else
      (cd "$ROOT/web" && "$bin/eslint" "${js_files[@]}") || status=1
    fi
  fi
  if [[ -x "$bin/prettier" ]]; then
    if [[ "$mode" == "--fix" ]]; then
      (cd "$ROOT/web" && "$bin/prettier" --write --log-level warn "${fe_files[@]}") || status=1
    else
      (cd "$ROOT/web" && "$bin/prettier" --check --log-level warn "${fe_files[@]}") || status=1
    fi
  fi
  if [[ ! -x "$bin/tsc" ]]; then
    echo "lint: web/node_modules not installed (cd web && npm ci); web files skipped." >&2
  fi
fi
exit $status
