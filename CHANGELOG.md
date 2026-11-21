# Changelog

Written for agents. Newest entry first. Each commit adds one entry at the top, using the format in `AGENTS.md` section 3. Read the newest entries before planning or changing anything. They record what changed after the docs were written.

## 2026-11-21 · docs(infra): document the AWS deployment
- **Changed:** `docs/infrastructure.md` covers architecture, sizing, blue/green, `deploy.sh plan|apply`, tag scheme, Route 53 + ACM variables and the backlog. `docs/docker.md` links to it.
- **Why:** AGENTS.md requires docs with each behavior change.
- **Agents:** Backlog items have no issue numbers: `scripts/issue.sh` is missing and the fork has issues disabled. Create them upstream when the team agrees. The two-target-group blue/green setup is validated by Terraform only; the ECS API confirms it at first apply.
- **Files:** `docs/infrastructure.md`, `docs/docker.md`.
## 2026-11-21 · feat(infra): add deploy.sh with plan and apply phases
- **Changed:** `infrastructure/deploy.sh plan` checks the AWS account (402909940511), creates the versioned, encrypted state bucket `cascadasen-tfstate-402909940511` if missing, runs init/fmt/validate/plan and writes `infrastructure/.deploy-tag`. `apply` creates ECR, builds and pushes both images (`linux/amd64`), then applies a fresh plan and prints the CloudFront URL. `terraform.tfvars.example` lists the optional variables.
- **Why:** The user runs deploys with their own credentials; plan and apply are split so the plan is reviewed first.
- **Agents:** Credentials come from the environment, else the keys file (never printed, no `AWS_PROFILE`). Image tag is the short commit, plus `-dirty-<UTC time>` when `backend`, `web`, `data` or `infrastructure/docker` have uncommitted changes. ECR is immutable, so `apply` skips a build when the tag already exists. `apply` aborts if the tree changed since `plan`. Only run `apply` after the user approves the plan.
- **Files:** `infrastructure/deploy.sh`, `infrastructure/terraform.tfvars.example`.
## 2026-11-21 · feat(infra): add Terraform stack for ECS Fargate behind ALB and CloudFront
- **Changed:** `infrastructure/*.tf` defines a VPC with 2 public subnets, an ALB (production listener :80, test listener :8080, 4 target groups), one ECS Fargate service (1 task, 2 vCPU / 4 GB, containers `backend` :8000 and `web` :80) with native ECS blue/green on two `load_balancer` blocks, two immutable ECR repos, CloudWatch logs, and a CloudFront proxy (no cache, redirect to HTTPS). State uses an S3 backend with `use_lockfile`.
- **Why:** POC deployment requested by the team. An ALB cannot hold an Elastic IP, so CloudFront points to the ALB DNS name.
- **Agents:** Variables: `image_tag` (required, set by deploy.sh), `domain_name`, `cloudfront_certificate_arn`, `origin_https`, `alb_certificate_arn` (all optional). ECS rewrites the listener-rule forward actions on each deployment, so those rules use `ignore_changes = [action]`. No Route 53 resources yet. Never run `terraform apply` by hand; `infrastructure/deploy.sh` comes in the next commit.
- **Files:** `infrastructure/*.tf`, `infrastructure/.terraform.lock.hcl`.
## 2026-11-21 · feat(docker): add docker compose stack for backend and web
- **Changed:** `docker-compose.yml` runs `backend` (FastAPI, :8000) and `web` (Vite dev server with npm, :5173). `backend/Dockerfile` installs from `uv.lock`. `web/Dockerfile` uses `npm ci`; compose bind-mounts `./web` and `./data` because the app imports `../data/processed`. Optional `data-build` profile rebuilds `data/processed`. Host ports are configurable with `WEB_PORT` and `BACKEND_PORT`. Root `.gitignore` also ignores `node_modules/`, `dist/`, `.env.local`, `.DS_Store` and `.playwright-mcp/`.
- **Why:** Run and simulate the whole project locally with only Docker installed.
- **Agents:** Start everything with `docker compose up --build`. Details in `docs/docker.md`. The services are independent: the web app does not call the backend. `?mapa=2` needs `web/.env.local` with `VITE_MAPBOX_TOKEN`. Keep `backend/uv.lock` and `web/package-lock.json` current, the images install with `--locked` / `npm ci`.
- **Files:** `docker-compose.yml`, `backend/Dockerfile`, `backend/.dockerignore`, `web/Dockerfile`, `web/.dockerignore`, `docs/docker.md`, `docs/stack.md`, `.gitignore`.

## 2026-11-21 · docs(cyber): reframe as hackathon resilience scenarios

- **Changed:** `docs/cyber.md` now opens with a context paragraph: hackathon simulation-track project, educational and preventive, grid-level effects only. Attacker-centred wording is replaced by resilience and continuity-planning terms. The "attack vs random failure" table is now "what a resilience study must represent beyond classic N-1". Classes renamed: C4 "Defence not acting", C5 "Loss of remote dispatch", C6 "Combined stress test".
- **Why:** The old wording read like attack planning even though the content was already consequence-only. The purpose should be explicit.
- **Agents:** Data, sources, section numbers and IDs (C1-C6, Q1-Q6, L0-L3, V7/V10) and contract field names are unchanged, so cross-references still hold. Write about this scenario family as "cyber incident" or "disturbance" effects, never from an attacker's point of view. `idea.md` and `AGENTS.md` still say "consequences of cyberattacks" in a few lines; align them if touched.
- **Files:** `docs/cyber.md`.

## 2026-11-21 · docs(tasks): assign owners and add cost, market and DIgSILENT tasks

- **Changed:** `docs/tasks.md` assigns Vale and Ignacio to "New features" and to the count of people affected by blackouts. It adds three tasks: market values (Ignacio, Valentina); estimating the values and costs of the 25F blackout and of the solar plant hack; and studying DIgSILENT.
- **Why:** Team task update.
- **Agents:** `docs/tasks.md` belongs to the team; do not overwrite it. The "solar plant hack" task is the Huatacondo case documented in `docs/cyber.md` section 2. Blackout costs use the CNE failure cost [19] (`docs/stack.md` section 6.1).
- **Files:** `docs/tasks.md`.

## 2026-11-21 · docs: link agent workflow from stack and plan

- **Changed:** The decisions table in `docs/stack.md` now lists the CI lint and the agent tooling, and section 9 points to `AGENTS.md`. Section 10 of `docs/plan.md` starts with `AGENTS.md`, the newest changelog entries and the git hook setup.
- **Why:** So that the docs read order leads to the workflow rules.
- **Agents:** `AGENTS.md` is the single source for workflow rules. `stack.md` only links to it.
- **Files:** `docs/stack.md`, `docs/plan.md`.

## 2026-11-21 · chore(agents): add AGENTS.md, CLAUDE.md and Claude Code hooks

- **Changed:** `AGENTS.md` holds the rules for every agent: read the docs before every plan and change, lint, one changelog entry per commit, conventions, tooling map. `CLAUDE.md` imports it. `.claude/settings.json` adds four hooks: lint the edited file (PostToolUse), block `git commit` without a staged `CHANGELOG.md` (PreToolUse), inject the docs read order and newest entries (SessionStart), and a reminder on each prompt (UserPromptSubmit). `.gitignore` now ignores `.claude/settings.local.json`.
- **Why:** Ricardo asked that agents read the docs before each plan and change, and that every change be linted and logged.
- **Agents:** Read `AGENTS.md` first. Fix what the lint hook reports. When a commit is blocked, write the changelog entry. This overlaps with Alonso's "Agentic setup" task in `docs/tasks.md`; coordinate before changing the tooling.
- **Files:** `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/*`, `.gitignore`.

## 2026-11-21 · ci: add ruff and changelog check workflow

- **Changed:** `.github/workflows/lint.yml` runs `ruff check` and `ruff format --check` on `backend/` with ruff 0.17.6, the version in `uv.lock`. On pull requests it fails when `CHANGELOG.md` did not change.
- **Why:** Enforce lint and the changelog remotely, not only on machines that have the hooks enabled.
- **Agents:** The workflow has not run on GitHub yet. Check its first run.
- **Files:** `.github/workflows/lint.yml`.

## 2026-11-21 · chore(lint): add shared lint script and git pre-commit hook

- **Changed:** `scripts/lint.sh --fix|--check FILE...` runs ruff on Python files and eslint/prettier on `frontend/` files once those tools are installed. It skips every other file. `scripts/hooks/pre-commit` lints the staged files and requires a staged `CHANGELOG.md`. Merge commits are exempt; `SKIP_CHANGELOG=1` covers exceptions.
- **Why:** Every change is linted with the right tool, and hooks, CI and humans share one entry point.
- **Agents:** Run `git config core.hooksPath scripts/hooks` once per clone. The hook checks the working-tree copy of each staged file.
- **Files:** `scripts/lint.sh`, `scripts/hooks/pre-commit`.

## 2026-11-21 · docs(cyber): simulation objective is the consequence of cyberattacks

- **Changed:** New `docs/cyber.md`: the main objective of the simulation is to estimate the consequences of cyberattacks on the SEN, modelling the effect and never the technique. It includes questions Q1-Q6, scenario classes C1-C6, consequence levels L0-L3, validation case V10 (Huatacondo, Aug 2026), dual-use guardrails and data gaps. `idea.md`, `plan.md`, `stack.md` (section 6.1, optional `timeline.json` fields and API fields) and `datasets.md` (sources [34]-[39]) were updated to match.
- **Why:** Requested by Ricardo on 2026-11-21. Public case: the Huatacondo plant (103 MW PV + 98 MW / 312 MWh battery) in Tarapaca, disconnected on 27 Aug 2026 after a cyberattack.
- **Agents:** Read order is now `idea.md` -> `cyber.md` -> `stack.md` -> `datasets.md` -> `plan.md`. The older rule "say failure, not attack" was replaced by "describe events by effect, never by attack technique". The no-minimum-cut rule stays. The team has not confirmed the framing yet (`plan.md` section 9, item 10). Huatacondo facts come from pv magazine (secondary source); the Ukraine figures are not verified.
- **Files:** `docs/cyber.md`, `docs/idea.md`, `docs/plan.md`, `docs/stack.md`, `docs/datasets.md`.

## 2026-11-21 · docs(changelog): add agent-facing changelog backfilled from history

- **Changed:** Added `CHANGELOG.md`. Each entry's heading is the commit subject, followed by Changed, Why, Agents and Files. Earlier commits were backfilled from the git history.
- **Why:** Each commit should leave a short summary that tells the next agent what changed.
- **Agents:** Add one entry at the top with every commit.
- **Files:** `CHANGELOG.md`.

## 2026-11-21 · feat(data): unified SEN grid data API and test map (6bc580a, merged in #1)

- **Changed:** Added the `backend/` package `cascadasen` (ports and adapters). It unifies IDE Energia, CEN Infotecnica, PyPSA-CL `Topology.xlsx` and INE Censo 2024 into one grid graph, runs 18 validation checks on each build, and serves a read-only FastAPI at `/api/v1` plus a deck.gl test map at `/map`. Processed outputs are committed in `data/processed/`.
- **Why:** The team needed one verified data source for the grid before building the map and the engine.
- **Agents:** Commands: `cd backend && uv run cascadasen-build`, `uv run cascadasen-api`, `uv run pytest`. To add a source, write one adapter implementing `GridDataSource` and register it in `infrastructure/container.py`. The raw cache `data/raw/` is git-ignored. Details in `backend/README.md` and `docs/datasets.md` section 0.
- **Files:** `backend/`, `data/processed/`, `docs/datasets.md`.

## 2026-11-21 · docs(stack): revise architecture around frontend-only MVPs (d024d44)

- **Changed:** The first MVPs are frontend only and read hand-written fixtures. Engine, API, precompute, CI and LLM were marked as backlog.
- **Why:** Planning session of 2026-11-21.
- **Agents:** Fixture numbers must carry an "assumption" or "fixture" label. The engine will later write files in the same format as the fixtures.
- **Files:** `docs/stack.md`.

## 2026-11-21 · docs: ideas, tasks and plan (ed87ffa)

- **Changed:** Added `docs/idea.md`, `docs/stack.md`, `docs/datasets.md`, `docs/plan.md` and `docs/tasks.md`.
- **Why:** The team chose the CascadaSEN idea (grid blackout simulator, 25F validation).
- **Agents:** `docs/tasks.md` belongs to the team; do not overwrite it.
- **Files:** `docs/`.

## 2026-11-21 · Platanus template (2c494db..8763198)

- **Changed:** Organiser template: `README.md`, `platanus-hack-project.jsonc`, `project-description.md`, `project-logo.png`.
- **Agents:** The metadata is still `<FILL THIS>` (`plan.md` section 8). The README's banana-emoji line is part of the template; ask the team before touching it.
- **Files:** root template files.
