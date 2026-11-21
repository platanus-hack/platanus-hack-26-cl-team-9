# Agent instructions: CascadaSEN

These rules apply to every coding agent (Claude Code, Codex, Cursor, others) and to the humans on the team. Claude Code loads them through `CLAUDE.md`.

## 1. Before planning or changing anything: read the docs

Do this before each plan and before each change, not only at the start of a session.

1. Read the docs that apply, in this order:
   1. `docs/idea.md`: product, scope, limits, risks
   2. `docs/cyber.md`: main objective of the simulation (consequences of cyberattacks) and its guardrails
   3. `docs/stack.md`: architecture, simulation model, data contracts, conventions
   4. `docs/datasets.md`: data sources, pipeline, provenance rule
   5. `docs/plan.md`: phases, validation cases, priorities, open decisions (section 9)
   6. `backend/README.md` for backend work
   For a small change, reading the sections the change touches plus `plan.md` section 9 is enough. A plan that contradicts the docs must say so explicitly.
2. Read the newest entries of `CHANGELOG.md`. They say what changed after the docs were written.
3. Check `git status` and `git log --oneline -10`. Do not overwrite uncommitted work from someone else.
4. When the docs and the code disagree, the code is the current state. Fix the doc in the same change.
5. Do not re-research what the docs already record. Verify only what the task needs and write new findings into the docs.

## 2. While changing

- **Lint every change when a linter applies.** Run `scripts/lint.sh --fix <files>`:
  - Python: `ruff check --fix` and `ruff format`, configured in `backend/pyproject.toml`.
  - Frontend (`frontend/`): eslint and prettier, as soon as `frontend/package.json` installs them. Until then the script skips frontend files.
  - Markdown and data files: no linter.
  Claude Code runs this automatically after every edit (section 5). Other agents run it themselves before committing.
- **Tests:** after backend changes, run `cd backend && uv run pytest`.
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
| Claude Code: docs read order + latest changelog entries | `.claude/hooks/session_context.sh` (SessionStart) | At session start, resume and after compaction |
| Claude Code: reminder to read the docs | `.claude/hooks/docs_reminder.sh` (UserPromptSubmit) | On every prompt |
| CI: ruff + changelog check on pull requests | `.github/workflows/lint.yml` | Every push and pull request |

Hook configuration lives in `.claude/settings.json`, which is committed and shared. Personal overrides go in `.claude/settings.local.json`, which is git-ignored.
