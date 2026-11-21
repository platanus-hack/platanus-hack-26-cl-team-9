#!/usr/bin/env bash
# Claude Code SessionStart hook.
# Injects the docs read order and the latest CHANGELOG entries into the session,
# so every plan starts from the current docs.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

latest=""
if [[ -f "$ROOT/CHANGELOG.md" ]]; then
  # The three newest entries (each starts with "## ").
  latest="$(awk '/^## /{n++} n>=1 && n<=3' "$ROOT/CHANGELOG.md")"
fi

msg="Sub50 project rules (AGENTS.md):
- Before planning or changing anything, read the docs that apply, in this order: docs/idea.md -> docs/cyber.md -> docs/stack.md -> docs/design.md (UI work) -> docs/datasets.md -> docs/plan.md (backend work: also backend/README.md; frontend work: also web/README.md). Then read the latest CHANGELOG.md entries.
- Every edit is linted automatically (scripts/lint.sh: ruff for Python). Fix what the hook reports.
- Every commit adds an entry at the top of CHANGELOG.md (format in AGENTS.md section 3).

Latest CHANGELOG entries:
${latest:-"(none yet)"}"

jq -n --arg ctx "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
