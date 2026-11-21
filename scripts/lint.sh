#!/usr/bin/env bash
# Lint the given files with the right tool for each file type.
#
# Usage: scripts/lint.sh --fix|--check FILE...
#   --fix    apply safe fixes and formatting, then report what is left
#   --check  report only, change nothing (used by the git pre-commit hook and CI)
#
# Python      -> ruff check + ruff format (config: backend/pyproject.toml)
# frontend/*  -> eslint and prettier, once frontend/package.json installs them
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
    "$ROOT"/frontend/*.ts | "$ROOT"/frontend/*.tsx | "$ROOT"/frontend/*.js | "$ROOT"/frontend/*.jsx | \
    "$ROOT"/frontend/*.mjs | "$ROOT"/frontend/*.cjs | "$ROOT"/frontend/*.css | "$ROOT"/frontend/*.json)
      fe_files+=("$abs") ;;
  esac
done

status=0

# --- Python: ruff -----------------------------------------------------------
if ((${#py_files[@]})); then
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

# --- Frontend: eslint + prettier (only when installed) ----------------------
if ((${#fe_files[@]})); then
  bin="$ROOT/frontend/node_modules/.bin"
  js_files=()
  for f in "${fe_files[@]}"; do
    case "$f" in *.css | *.json) ;; *) js_files+=("$f") ;; esac
  done
  if [[ -x "$bin/eslint" ]] && ((${#js_files[@]})); then
    if [[ "$mode" == "--fix" ]]; then
      (cd "$ROOT/frontend" && "$bin/eslint" --fix "${js_files[@]}") || status=1
    else
      (cd "$ROOT/frontend" && "$bin/eslint" "${js_files[@]}") || status=1
    fi
  fi
  if [[ -x "$bin/prettier" ]]; then
    if [[ "$mode" == "--fix" ]]; then
      (cd "$ROOT/frontend" && "$bin/prettier" --write --log-level warn "${fe_files[@]}") || status=1
    else
      (cd "$ROOT/frontend" && "$bin/prettier" --check --log-level warn "${fe_files[@]}") || status=1
    fi
  fi
  if [[ ! -x "$bin/eslint" && ! -x "$bin/prettier" ]]; then
    echo "lint: frontend linters not installed yet (frontend/node_modules/.bin); skipped." >&2
  fi
fi

exit $status
