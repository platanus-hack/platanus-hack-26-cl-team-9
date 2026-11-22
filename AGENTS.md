# Agent instructions: Sub50

These rules apply to every coding agent (Claude Code, Codex, Cursor, others) and to the humans on the team. Claude Code loads them through `CLAUDE.md`.

## 1. Before planning or changing anything: read the docs

Do this before each plan and before each change, not only at the start of a session.

0. Find your way first (navigation, it does not replace the list below):
   - `llms.txt`: the repository in one page: what Sub50 is, then links grouped by topic (the llmstxt.org format).
   - `docs/README.md`: every doc with its purpose, when to read it and whether it is current, plus a "where is X" table.
   - `docs/code-map.md`: backend and web module by module, with file:line entry points, the data flow of a line cut, a session edit, an incident run and the assistant loop, and the tests that cover each module. Use `docs/for-reviewers.md` to check a claim.
   - `docs/index/repo-index.json`: look up a file, symbol, route, doc heading or covering test with `jq` instead of reading the tree (queries in `docs/index/README.md`). Regenerate it before you commit a change to a source, doc or test file, a route or `CHANGELOG.md`: `cd backend && uv run python ../scripts/build_index.py` (section 2).
1. Read the docs that apply, in this order:
   1. `docs/idea.md`: product, scope, limits, risks (and `docs/architecture.md` for how the system is built)
   2. `docs/cyber.md`: main objective of the simulation (consequences of cyberattacks) and its guardrails
   3. `docs/stack.md`: architecture, simulation model, data contracts, conventions
   4. `docs/design.md`: visual direction, colors, zoom levels, logo (for UI work)
   5. `docs/datasets.md`: data sources, pipeline, provenance rule
   6. `docs/plan.md`: phases, validation cases, priorities, open decisions (section 9)
   7. `backend/README.md` for backend work, `web/README.md` for frontend work
   8. `docs/strategy.md` and `docs/agents.md` for work on the strategic theatre and its agents
   9. `docs/sessions-api.md` for work on shared sessions or on external agents that call the API (every agent endpoint takes the session id in its path), and `docs/mcp.md` for the MCP server that lets a client run simulations in natural language, and `docs/assistant.md` for the in-app assistant (the same tools behind `POST /api/v1/assistant/chat`)
   10. `docs/regional.md` and `docs/network-format.md` for other countries' networks (drawn layers, Brazil's flow network, the data contract for adding or uploading a network)
   For a small change, reading the sections the change touches plus `plan.md` section 9 is enough. A plan that contradicts the docs must say so explicitly.
2. Read the newest entries of `CHANGELOG.md`. They say what changed after the docs were written.
3. Check `git status` and `git log --oneline -10`. Do not overwrite uncommitted work from someone else.
4. When the docs and the code disagree, the code is the current state. Fix the doc in the same change.
5. Do not re-research what the docs already record. Verify only what the task needs and write new findings into the docs.

## 2. While changing

- **Lint every change when a linter applies.** Run `scripts/lint.sh --fix <files>`:
  - Python: `ruff check --fix` and `ruff format`, configured in `backend/pyproject.toml`.
  - Frontend (`web/`): `tsc --noEmit` on the whole project when `web/node_modules` is installed (`cd web && npm ci`). eslint and prettier run only if they are installed there; they are not dependencies today.
  - Markdown and data files: no linter.
  Claude Code runs this automatically after every edit (section 5). Other agents run it themselves before committing.
- **Tests:** after backend changes, run `cd backend && uv run pytest`.
- **Repo index:** `docs/index/repo-index.json` is generated (files, public symbols, routes, doc headings, CHANGELOG headings; schema and `jq` queries in `docs/index/README.md`). Before each commit that adds, removes or edits a source, doc or test file, a route or `CHANGELOG.md`, `git add` new files and run `cd backend && uv run python ../scripts/build_index.py`, then stage the result. The CI job `repo-index` (`.github/workflows/checks.yml`) turns red while it is stale, but it never blocks a deploy.
- **Docs:** when behaviour, a data contract or a decision changes, update the doc in the same commit.

## 3. Every commit: changelog entry

Each commit adds one entry at the top of `CHANGELOG.md`, below the header, and stages it with the commit. The changelog is written for agents: the next agent reads it to learn what changed without reading the whole diff.

Entry format:

```markdown
## YYYY-MM-DD · type(scope): subject

- **Changed:** what changed, in 1-4 bullets.
- **Why:** the reason or the decision behind it.
- **Agents:** what an agent must know from now on: new files, commands, contracts, rules, open decisions, things that are now wrong in older docs.
- **Files:** main paths touched.
```

- The heading reuses the commit subject. Commit messages follow Conventional Commits with a scope, as in the history: `feat(data): ...`, `docs(cyber): ...`, `chore(agents): ...`.
- One entry per commit. If a commit is amended, update its entry instead of adding a new one.
- Merge commits need no entry. For an exceptional commit that needs none, use `SKIP_CHANGELOG=1 git commit ...` and say why in the commit message.

Enforcement:
- Git hook `scripts/hooks/pre-commit` checks lint and the changelog for everyone. Enable it once per clone: `git config core.hooksPath scripts/hooks`.
- Claude Code also blocks `git commit` without a staged `CHANGELOG.md` (section 5).
- CI (`.github/workflows/lint.yml`) runs ruff and checks that each pull request changes `CHANGELOG.md`.

## 4. Conventions (details in `docs/stack.md` section 9)

- Code, comments and docs in English. UI strings and narration in Spanish.
- `docs/tasks.md` belongs to the team. Do not overwrite it.
- Every number shown in the UI carries a source or `is_assumption: true` (`docs/datasets.md` section 6).
- Cyber scenarios model the effect, never the attack technique. No feature searches for the worst attack (`docs/cyber.md` section 8).
- Real, small commits during the event.

## 5. Tooling map

| What | Where | When it runs |
|---|---|---|
| Shared linter entry point | `scripts/lint.sh --fix\|--check FILE...` | Called by every hook below and by hand |
| Git pre-commit: lint staged files + require `CHANGELOG.md` | `scripts/hooks/pre-commit` | Every `git commit`, after `git config core.hooksPath scripts/hooks` |
| Claude Code: lint the edited file | `.claude/hooks/lint_changed_file.sh` (PostToolUse on Edit/Write/MultiEdit) | After every file edit; leftover problems are sent back to Claude |
| Claude Code: block a commit without a changelog entry | `.claude/hooks/check_changelog_on_commit.sh` (PreToolUse on Bash) | Before every `git commit` |
| Regenerate the repo index (`docs/index/repo-index.json`) | `cd backend && uv run python ../scripts/build_index.py` (`--check` to verify) | By hand before a commit; `tests/integration/test_repo_index.py` checks it in the non-blocking CI job `repo-index` |
| Claude Code: docs read order + latest changelog entries | `.claude/hooks/session_context.sh` (SessionStart) | At session start, resume and after compaction |
| Claude Code: reminder to read the docs | `.claude/hooks/docs_reminder.sh` (UserPromptSubmit) | On every prompt |
| CI: ruff + changelog check on pull requests | `.github/workflows/lint.yml` | Every push and pull request |

Hook configuration lives in `.claude/settings.json`, which is committed and shared. Personal overrides go in `.claude/settings.local.json`, which is git-ignored.
