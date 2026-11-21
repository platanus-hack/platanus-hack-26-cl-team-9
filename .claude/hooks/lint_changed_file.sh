#!/usr/bin/env bash
# Claude Code PostToolUse hook (Edit|Write|MultiEdit).
# Runs scripts/lint.sh --fix on the file that was just edited. If problems remain
# after the auto-fix, exits 2 so Claude sees them and fixes them.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
f="$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')"

[[ -n "$f" && -f "$f" ]] || exit 0
case "$f" in "$ROOT"/*) ;; *) exit 0 ;; esac   # only files inside this repo

out="$("$ROOT/scripts/lint.sh" --fix "$f" 2>&1)"
rc=$?
if ((rc != 0)); then
  {
    echo "Lint problems remain in $f after auto-fix (scripts/lint.sh --fix). Fix them before continuing:"
    echo "$out"
  } >&2
  exit 2
fi
exit 0
