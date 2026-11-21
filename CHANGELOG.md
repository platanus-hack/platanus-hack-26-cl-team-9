# Changelog

Written for agents. Newest entry first. Each commit adds one entry at the top, using the format in `AGENTS.md` section 3. Read the newest entries before planning or changing anything. They record what changed after the docs were written.

## 2026-11-21 · feat(web): mapa 3 interface following the Paper design (#28)

- **Changed:** New layout (`.shell` in `styles.css`): a collapsible rail on the left (Sub50, Mapa, Supuestos; the collapsed state is saved in localStorage), a floating panel with the tabs Red, Simulación, Leyenda and Supuestos (the last two used to sit at the bottom of the old right panel), a timeline card at the bottom of the panel (play, scrubber, stage and seconds), the case selector as a pill at the top center of the map, and the 2D/3D toggle plus zoom buttons at the top right. The camera now leaves room on the left, and the Mapbox logo moved to the bottom right. Neutral charcoal colors instead of navy.
- **Why:** The team asked for the full interface of the Paper mockup, with Red and Simulación within reach and the legend and assumptions as tabs.
- **Agents:** Mapa 3 only; the deprecated mapas 1 and 2 keep the old `.layout` and `.panels`. `BaseMap` has a new `zoomBy()`. The camera clearance (`PANEL_CLEARANCE_PX`, 640) is fixed: collapsing the rail does not re-center the map. Not built: rail items Escenarios, Validación, Datos y fuentes, Metodología and Ayuda; tabs Qué lo habría evitado and Validación; the date pill; the "Color de líneas: Tensión" legend and mode; scale bar and layers button; Hz and speed in the timeline.
- **Files:** `web/src/cascade/CascadeApp.tsx`, `web/src/cascade/Legend.tsx`, `web/src/map/baseMap.ts`, `web/src/styles.css`.

## 2026-11-21 · feat(web): Red panel with network summary and node detail (#26)

- **Changed:** The right panel of mapa 3 has two tabs, Red and Simulación (the previous results block). Red shows the Paper design: km of lines (34.578), substations (1.220), installed MW (38.203) and km by voltage band, computed in the browser from `data/processed/geo/{lines,substations,plants}.geojson` (`web/src/cascade/networkSummary.ts`; the numbers match the mockup exactly). Clicking a substation (3D bar, 2D disc or node dot) opens its detail in Red: kV, zone, generation, demand, people, and its connected lines with their loading at the current stage; clicking one of those lines cuts it. A cut line also gets a detail card (capacity, flow, loading). Cutting a line switches to Simulación.
- **Why:** The design has a Red tab; the team asked to visualise each node or line with the data we have.
- **Agents:** Clicking a line on the map still cuts it (not changed). Node data is the reduced network (188 buses); the summary is the full IDE data (1.220 substations), so the two counts differ on purpose. `people` has the known defect (substations with load and 0 people, for example S/E Mauro). Not built: tabs Qué lo habría evitado and Validación, the nav rail, inertia or sync MW per node (not in the cache), per-plant detail.
- **Files:** `web/src/cascade/NetworkPanel.tsx`, `networkSummary.ts` (+ test), `CascadeApp.tsx`, `web/src/styles.css`.

## 2026-11-21 · feat(web): seven more icons for the 2D view (#24)

- **Changed:** Added `plant-hydro`, `plant-gas`, `plant-geothermal`, `plant-biomass`, `grid-tower`, `grid-breaker` and `grid-transformer` (512 px PNG) to the icon folder, and the matching kinds to `IconKind` in `web/src/cascade/icons.ts`. Now 12 icons. All icons live in `web/src/assets/icons/` (moved from `web/public/icons/`, where #23 put the first five) and are imported with `?url` in `icons.ts`, so Vite bundles and hashes them.
- **Why:** The 2D view needs an icon per generation carrier in the data and per grid element in `design.md`.
- **Agents:** Still no icon is drawn: nothing passes `icons` to the View yet. `plant-biomass` is an ASSUMPTION (the image is a plant with a sprout and wind, named `green-factory` by its source). Still missing: diesel, CSP (solar thermal), substation, pole, gantry. `grid-tower.png` is dark gray; the others are black. `mask: true` tints all of them, so the color of the file does not matter.
- **Files:** `web/src/assets/icons/*`, `web/src/cascade/icons.ts`.

## 2026-11-21 · feat(web): 2D view = same map from above, with flat symbols (#22)

- **Changed:** 2D keeps the same Mapbox Standard (night) basemap as 3D and only looks straight down: camera pitch 0 and rotation disabled. The 3D demand bars are replaced by flat discs whose radius grows with the square root of MW (layer id `load-2d`). New 2D-only icon layer: `IconPoint` and `iconLayers()` in `web/src/cascade/icons.ts`, sized in meters on the ground (clamped to 12 to 40 pixels) so icons scale with the zoom. Image files in `web/src/assets/icons/` (`plant-coal`, `plant-wind`, `plant-solar`, `storage-battery`, `power-bolt`; 512 px PNG, black outline on transparent, tinted at draw time with `mask: true`). The legend text changes with the mode.
- **Why:** A different flat basemap (dark-v11) looked worse than the main map. The team chose the same 3D scene seen from above with 2D symbols, so icons can be added without 3D polygons.
- **Agents:** To add icons, build `IconPoint[]` and pass it as `icons` in the `View` given to `buildCascadeLayers` (`CascadeApp.tsx`, `_animate`). Nothing passes it yet, so no icon draws. Plant icons need per-plant data that the cache does not have (`node_index.json` `plants[]` has it). The Standard style still draws 3D buildings and terrain when zoomed in, even in 2D. The offline map (no token) only gets the camera lock. Branched from `feature/21-cities-metadata` (#21); this PR includes that commit until #21 merges.
- **Files:** `web/src/map/baseMap.ts`, `web/src/cascade/layers.ts`, `web/src/cascade/icons.ts`, `web/src/cascade/Legend.tsx`, `web/src/cascade/CascadeApp.tsx`.

## 2026-11-21 · fix(web): city labels become metadata, not drawn (#20)

- **Changed:** The city labels of #19 are no longer drawn. The list moved to `web/src/cascade/cities.ts` (`CITIES`) as data only.
- **Why:** Mapbox already labels these cities, so each name showed twice.
- **Agents:** Nothing imports `CITIES` yet. Use it for search, camera jumps or a breadcrumb. The "city labels" entry below is superseded: those labels are gone from the screen.
- **Files:** `web/src/cascade/layers.ts`, `web/src/cascade/cities.ts`, `CHANGELOG.md`.

## 2026-11-21 · feat(web): city labels in mapa 3 (#18)

- **Changed:** Six reference cities (Arica, Antofagasta, Calama, Santiago, Concepción, Puerto Montt) drawn as a cream dot plus a text label, in deck.gl (`CITIES` in `web/src/cascade/layers.ts`), on top of the grid layers.
- **Why:** The Paper design (`2d.css`) has these labels. It placed them with fixed pixels on a 1440x900 artboard; real coordinates keep them in place when the map zooms or moves.
- **Agents:** The labels are not pickable. Mapbox draws its own city names too, so some appear twice at some zooms. Font is Geist if installed, else system-ui; Geist is not bundled. Branched from `feature/toggle-2d` (#17), so this PR includes that commit until #17 merges.
- **Files:** `web/src/cascade/layers.ts`, `CHANGELOG.md`.

## 2026-11-21 · feat(web): 2D / 3D toggle in mapa 3 (#16)

- **Changed:** A 2D / 3D button at the top of the map (left of the panel). 3D is the previous view: camera pitch 45 and rectangular demand bars. 2D sets pitch 0 and draws demand as flat discs (radius grows with the square root of MW). `?vista=2d` opens in 2D. `BaseMap` has a new `setMode()` for both the Mapbox and the offline map.
- **Why:** The new interface (Paper, design.md) wants the same map in 2D and 3D. This is the toggle only; the nav rail, tabs, city labels and the new colours are not built.
- **Agents:** The 2D demand layer has its own id (`load-2d`). Reusing the id `load` for a different layer class makes deck.gl throw an accessor error. In 2D the discs replace the bars, so there is no height encoding.
- **Files:** `web/src/map/baseMap.ts`, `web/src/cascade/layers.ts`, `web/src/cascade/CascadeApp.tsx`, `web/src/styles.css`.

## 2026-11-21 · feat(web): mapa 3 is the main map; mapas 1 and 2 deprecated (#14)

- **Changed:** `/` and `?mapa=3` open mapa 3 (the cascade viewer). `?mapa=1` (offline deck.gl map) and `?mapa=2` (Mapbox basemap) still work but log a deprecation warning. No code was deleted.
- **Why:** The team chose mapa 3 as the product map. It is the only one with the engine, the legend and the cascade replay.
- **Agents:** Build new UI on `web/src/cascade/`, not on `web/src/map/chileMap.ts` or `mapboxMap.ts`. `docs/mapa3.md` and `docs/minimum-dataset.md` (merged in #12 without a changelog entry) describe the engine, the actors and the minimum dataset. The cache in `web/public/cache/` must be generated (`cascadasen-cache`) or the root page shows an error. Older docs that call `/` "the offline map" (`stack.md`, `docker.md`, `datasets.md`) are out of date on that point.
- **Files:** `web/src/main.tsx`, `web/README.md`, `docs/mapa3.md`, `CHANGELOG.md`.

## 2026-11-21 · chore(project): enlarge Sub50 logo wordmark

- **Changed:** `project-logo.png` is replaced with a version of the same logo (option 01) where the wordmark fills more of the 1000 x 1000 square. 40 KB PNG. `docs/design.md` section 6 updated.
- **Why:** The previous file had a lot of empty margin, so the logo looked small at the README's 200 px.
- **Agents:** Same design as before, only the scale changed. A small-size version is still open.
- **Files:** `project-logo.png`, `docs/design.md`.

## 2026-11-21 · chore(project): align oneliner and project page with the description

- **Changed:** `project-oneliner-spanish` in `platanus-hack-project.jsonc` now condenses `project-description-spanish` into one line: the agent first simulation plus its purpose (finding the most fragile points). `project-description.md` reuses the description's wording ("agent first", "en vivo la infraestructura crítica", "con datos públicos", "conectarse a nuestra API") and keeps its headings and bullets.
- **Why:** The three submission texts said the same thing with slightly different wording.
- **Agents:** `project-description-spanish` is the source text. Change the oneliner and `project-description.md` along with it.
- **Files:** `platanus-hack-project.jsonc`, `project-description.md`.

## 2026-11-21 · chore(project): set Sub50 deploy URL

- **Changed:** `deploy-url` in `platanus-hack-project.jsonc` is now `https://sub50.cl`.
- **Why:** The hackathon submission needs the public URL of the running project.
- **Agents:** All Platanus metadata fields are now filled (`plan.md` section 8). On 2026-11-21 the domain did not resolve yet (no DNS record); check that it serves the app before the submission deadline.
- **Files:** `platanus-hack-project.jsonc`.

## 2026-11-21 · chore(project): add Sub50 logo

- **Changed:** `project-logo.png` replaces the Platanus template logo with the Sub50 logo (option 01, Subscript: "sub" with a subscript "5" and a power-button "0", black on white, 1000 x 1000 PNG, 36 KB). `docs/design.md` sections 1, 6 and 7 record the pick.
- **Why:** The hackathon submission needs a 1000 x 1000 PNG logo under 500 KB.
- **Agents:** The logo is chosen, so do not reopen the logo pick. A small-size version without fine detail is still open. The README embeds the logo at 200 px.
- **Files:** `project-logo.png`, `docs/design.md`.

## 2026-11-21 · chore(project): set Sub50 description in project metadata

- **Changed:** `project-description-spanish` in `platanus-hack-project.jsonc` now holds the final team description (one paragraph that opens with the agent-first framing, then the map, blackout propagation and agent API). `project-name` stays "Sub50".
- **Why:** The hackathon submission reads name and description from this file.
- **Agents:** Do not rewrite the description without the team's approval. `deploy-url` is still `<FILL THIS>`. `project-oneliner-spanish` and `project-description.md` were not changed.
- **Files:** `platanus-hack-project.jsonc`.

## 2026-11-21 · docs: sync docs with the Sub50 name, design sessions and merged work

- **Changed:** New `docs/design.md`: Paper file and pages, Electricity Maps style, voltage and technology palette, 5 zoom levels, data behind the mockups, logo options. Product name Sub50 in titles and summaries (`idea.md`, `AGENTS.md`, `cyber.md`, both READMEs, session hook). `stack.md` now matches the repo (status, Mapbox option, engine base case, real layout, frontend section defers to `design.md`). `plan.md` repo state, submission checklist and open decisions 11-13. `datasets.md` adds the operating points and DC-OPF scripts and sources [40] Mapbox and [41] OpenStreetMap. Backfilled changelog entries for #2, #6, #7, #10 and the Sub50 project-page commit.
- **Why:** The design sessions of 2026-11-21 and five merges changed the product name, the visual direction and the repo state without updating the docs.
- **Agents:** Read order now includes `design.md` after `stack.md` for UI work; it overrides `stack.md` section 5 on visuals. Keep `cascadasen` as the package and command name. Open decision 11 in `plan.md` section 9: the attacker/defender agent framing in `project-description.md` conflicts with `cyber.md` section 8; keep following `cyber.md` until the team decides. `docs/tasks.md` was not touched.
- **Files:** `docs/design.md`, `docs/idea.md`, `docs/stack.md`, `docs/plan.md`, `docs/datasets.md`, `docs/cyber.md`, `AGENTS.md`, `web/README.md`, `backend/README.md`, `.claude/hooks/session_context.sh`, `CHANGELOG.md`.

## 2026-11-21 · feat: node popup, PyPSA-CL demand and a secure DC-OPF base case (cdc2ba0, #10; entry backfilled)

- **Changed:** `data/scripts/build_node_index.py` writes `node_index.json`, read by a click popup in `web/` (`src/map/nodeDetail.ts`) with everything known about a node. `build_operating_points.py` writes demand per bus from PyPSA-CL and merit-order dispatch for 4 operating points. `build_baseline_opf.py` writes a DC-OPF base case per point with no branch above s_nom and an inertia floor.
- **Why:** An overload cascade needs a realistic, secure starting point: how much each bus consumes and generates without overloaded lines.
- **Agents:** Dispatch and demand are simulated from PyPSA-CL inputs, not measured; show them as such. N-1 is not enforced. PyPSA-CL storage units are model candidates, not real batteries. Details in `docs/datasets.md` section 0.
- **Files:** `data/scripts/`, `data/processed/{node_index,operating_points,baseline_opf}.json`, `web/src/map/`.

## 2026-11-21 · feat(infra): attach ACM certificate and Route 53 alias to CloudFront for sub50.cl
- **Changed:** `domain_name` (default `sub50.cl`) drives the zone, the ACM certificate and the CloudFront alias. CloudFront uses the validated certificate (SNI, TLS 1.2 minimum). Apex `A` and `AAAA` alias records point to the distribution. New output `site_url`. The variable `cloudfront_certificate_arn` is removed.
- **Why:** Serve the app on `https://sub50.cl` through CloudFront.
- **Agents:** `aws_acm_certificate_validation` needs `sub50.cl` delegated to the Route 53 name servers (done by the user). Apply with `infrastructure/deploy.sh apply`, which sets `image_tag`. Origin HTTPS stays off; it needs an `alb.sub50.cl` record first (see backlog in `docs/infrastructure.md`).
- **Files:** `infrastructure/*.tf`, `infrastructure/terraform.tfvars.example`, `docs/infrastructure.md`.
## 2026-11-21 · docs(infra): marker line for second deploy

- **Changed:** One marker line in `docs/infrastructure.md`.
- **Why:** New commit gives a new image tag, so the second deploy proves the blue/green swap.
- **Agents:** Previous deploy: task definition `cascadasen:2`, tag `aade205`.
- **Files:** `docs/infrastructure.md`.
## 2026-11-21 · feat(infra): add ACM certificate for sub50.cl (not applied)
- **Changed:** `infrastructure/acm.tf` adds `aws_acm_certificate` (`sub50.cl` + `*.sub50.cl`, DNS), the validation records in the Route 53 zone and `aws_acm_certificate_validation`. Output `acm_certificate_arn`. Docs updated.
- **Why:** A certificate is needed for CloudFront and the ALB HTTPS listener before the domain goes live.
- **Agents:** Plan: 4 to add. Not applied; needs user approval. Apply only works once the registrar delegates `sub50.cl` to the zone's name servers, else validation waits and times out. The stack is deployed: CloudFront `https://d2bc0ohphbh56u.cloudfront.net`, image tag `aade205`, task definition `cascadasen:2`. Not attached to CloudFront yet.
- **Files:** `infrastructure/acm.tf`, `infrastructure/outputs.tf`, `docs/infrastructure.md`.
## 2026-11-21 · fix(infra): build images with buildx as Docker-format gzip layers
- **Changed:** `push_image` in `deploy.sh` uses `docker buildx build --provenance=false --sbom=false --output type=image,push=true,compression=gzip,force-compression=true,oci-mediatypes=false`.
- **Why:** Fargate failed with `CannotPullContainerError: wrong diff id` on images pushed with plain `docker build` + `docker push` from Colima (containerd image store, OCI manifest).
- **Agents:** `docker-buildx` is required (`brew install docker-buildx`, plugin linked in `~/.docker/cli-plugins`). ECR tag `probe1` in `cascadasen/backend` is a test push; ignore it. Images pushed under the old tag format are not usable.
- **Files:** `infrastructure/deploy.sh`.
## 2026-11-21 · fix(infra): auto-approve the targeted ECR apply in deploy.sh
- **Changed:** The ECR-only `terraform apply -target` in `deploy.sh apply` now passes `-auto-approve`.
- **Why:** The step prompted for `yes`, so a non-interactive `apply` hung. The user already approved the plan that includes the ECR repos.
- **Agents:** The full apply still uses the saved `tfplan` and needs no prompt. Run `plan` and get approval before `apply`.
- **Files:** `infrastructure/deploy.sh`.
## 2026-11-21 · docs(tasks): add animation, city and adversarial agent tasks

- **Changed:** `docs/tasks.md` gains animations with audio on attacked infrastructure, an affected people counter, city lights, a clickable city component (population, % dependent on electricity, deaths rising with blackout time) and an adversarial agents backlog item (attacker and resilience agents plus APIs, owner Ricardo).
- **Why:** The team refined the task list. The adversarial agents spec is backlog and is not written yet.
- **Agents:** Open questions are listed in each task (animation and sound mapping, death-rate model and its source, attacker objective and limits). The "% dependent on electricity" value needs a source or `is_assumption: true`. No code or contract changed.
- **Files:** `docs/tasks.md`.
## 2026-11-21 · feat(infra): add Route 53 hosted zone for sub50.cl
- **Changed:** `infrastructure/route53.tf` adds `aws_route53_zone.main` (`sub50.cl`). New output `route53_name_servers`. `docs/infrastructure.md` documents the zone and the NS delegation step.
- **Why:** The team will serve the app from sub50.cl; the zone must exist first so its name servers can be delegated at the .cl registrar.
- **Agents:** Zone only: no records, no ACM certificate, no CloudFront alias. The domain is not registered by Terraform. Plan is now 39 to add. `apply` still needs explicit user approval.
- **Files:** `infrastructure/route53.tf`, `infrastructure/outputs.tf`, `docs/infrastructure.md`.
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

## 2026-11-21 · chore(project): fill Sub50 name, description and project page (c33587e; entry backfilled)

- **Changed:** `platanus-hack-project.jsonc` and `project-description.md` now carry the name Sub50, a Spanish oneliner and description. `deploy-url` is still unfilled.
- **Why:** Platanus submission metadata.
- **Agents:** The product is Sub50. The description frames the project as AI agents attacking and defending the grid through an API, which conflicts with `cyber.md` section 8 (open decision 11 in `plan.md` section 9).
- **Files:** `platanus-hack-project.jsonc`, `project-description.md`.

## 2026-11-21 · docs(cyber): reframe as hackathon resilience scenarios

- **Changed:** `docs/cyber.md` now opens with a context paragraph: hackathon simulation-track project, educational and preventive, grid-level effects only. Attacker-centred wording is replaced by resilience and continuity-planning terms. The "attack vs random failure" table is now "what a resilience study must represent beyond classic N-1". Classes renamed: C4 "Defence not acting", C5 "Loss of remote dispatch", C6 "Combined stress test".
- **Why:** The old wording read like attack planning even though the content was already consequence-only. The purpose should be explicit.
- **Agents:** Data, sources, section numbers and IDs (C1-C6, Q1-Q6, L0-L3, V7/V10) and contract field names are unchanged, so cross-references still hold. Write about this scenario family as "cyber incident" or "disturbance" effects, never from an attacker's point of view. `idea.md` and `AGENTS.md` still say "consequences of cyberattacks" in a few lines; align them if touched.
- **Files:** `docs/cyber.md`.

## 2026-11-21 · chore: ignore all .env files except .env.example (b41f003, #7; entry backfilled)

- **Changed:** `.gitignore` ignores every `.env*` file except `.env.example`.
- **Why:** Keep tokens such as the Mapbox key out of the repo.
- **Agents:** Put secrets only in git-ignored env files. The web app reads `web/.env.local`.
- **Files:** `.gitignore`.

## 2026-11-21 · feat(web): mapa2, Mapbox vector basemap with the grid on top (a920317, #6; entry backfilled)

- **Changed:** `?mapa=2` mounts a Mapbox basemap (Standard, night) with the deck.gl grid layers on top through `MapboxOverlay`. The token comes from `VITE_MAPBOX_TOKEN` in `web/.env.local`; `web/.env.example` added. Without a token it falls back to the offline map.
- **Why:** Street-level context under the grid.
- **Agents:** This reverses the "no tile server" choice for this view only; the default map stays offline. Restrict the token by URL in the Mapbox account, since Vite bundles it.
- **Files:** `web/src/map/mapboxMap.ts`, `web/src/main.tsx`, `web/src/map/layers.ts`, `web/.env.example`, `web/README.md`.

## 2026-11-21 · feat(web): deck.gl map of Chile with the SEN grid in 3D (ce82cf2, #2; entry backfilled)

- **Changed:** New Vite + React + TypeScript app in `web/`: full-screen deck.gl map, lines by voltage, main-grid substations and generation columns per node from `data/processed/geo/`, a floating right legend panel, and a light Chile outline built by `data/scripts/build_chile_outline.sh`. Vitest covers plant-per-node aggregation.
- **Why:** First frontend MVP (`docs/stack.md` section 0): frontend only, no physics.
- **Agents:** Run with `cd web && npm install && npm run dev`. Before committing run `npx tsc --noEmit`, `npm test` and `npm run build`. Details in `web/README.md`.
- **Files:** `web/`, `data/scripts/build_chile_outline.sh`, `data/processed/chile.geojson`.

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
