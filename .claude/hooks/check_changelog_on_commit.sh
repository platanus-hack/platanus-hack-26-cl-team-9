#!/usr/bin/env bash
# Claude Code PreToolUse hook (Bash).
# Blocks `git commit` when CHANGELOG.md is not part of the commit, so every commit
# leaves an entry for the next agent. The git pre-commit hook enforces the same
# rule for humans and other agents; this one gives Claude the reason before git runs.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cmd="$(jq -r '.tool_input.command // empty')"

# Only `git commit ...` (also `git -C dir commit`).
grep -Eq '(^|[;&|(][[:space:]]*|[[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)' <<<"$cmd" || exit 0

# Escape hatches: explicit skip, or the same command stages the changelog.
grep -q 'SKIP_CHANGELOG=1' <<<"$cmd" && exit 0
grep -q 'CHANGELOG.md' <<<"$cmd" && exit 0

cd "$ROOT" || exit 0
[[ -f "$(git rev-parse --git-dir 2>/dev/null)/MERGE_HEAD" ]] && exit 0
git diff --cached --name-only | grep -qx 'CHANGELOG.md' && exit 0

# `git commit -a` / `-am` includes tracked, modified files.
if grep -Eq 'commit([^;&|]*[[:space:]])(-a|--all|-[a-zA-Z]*a[a-zA-Z]*)([[:space:]]|$)' <<<"$cmd"; then
  git diff --name-only | grep -qx 'CHANGELOG.md' && exit 0
fi

cat >&2 <<'EOF'
Commit blocked: CHANGELOG.md is not staged.
Add an entry at the top of CHANGELOG.md for this commit (format in AGENTS.md section 3),
then `git add CHANGELOG.md` and commit again.
EOF
exit 2
