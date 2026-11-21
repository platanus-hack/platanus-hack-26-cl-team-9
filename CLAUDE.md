@AGENTS.md

## Claude Code specifics

- Hooks in `.claude/settings.json` enforce `AGENTS.md`: every edited file is linted, `git commit` is blocked without a staged `CHANGELOG.md`, and the docs read order plus the latest changelog entries are injected at session start.
- When the lint hook reports problems, fix them in the same turn. Do not disable the hook.
- When a commit is blocked, write the changelog entry. Do not bypass the block with `SKIP_CHANGELOG=1` unless the user asks for it.
- In plan mode, read the docs (`AGENTS.md` section 1) before writing the plan, and cite the doc sections the plan relies on.
