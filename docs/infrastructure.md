# Infrastructure

AWS deployment of CascadaSEN: one Fargate task behind an ALB and CloudFront, defined in Terraform under `infrastructure/`.

## Images

Both images are built from the repo root with their own Dockerfile and per-Dockerfile ignore file (`<name>.Dockerfile.dockerignore`), for `linux/amd64`.

| Image | Dockerfile | Stack | Port | Health path |
|---|---|---|---|---|
| backend | `infrastructure/docker/backend.Dockerfile` | Python 3.12 + uv, `cascadasen-api`, `data/processed` baked in at `/data/processed` (`CASCADASEN_DATA_DIR=/data`) | 8000 | `/api/v1/health` |
| web | `infrastructure/docker/web.Dockerfile` | `npm run build` (node 22; reads `data/processed` at build time), served by nginx with SPA fallback (`infrastructure/docker/nginx.conf`) | 80 | `/healthz` |

```bash
docker build --platform linux/amd64 -f infrastructure/docker/backend.Dockerfile -t cascadasen-backend .
docker build --platform linux/amd64 -f infrastructure/docker/web.Dockerfile -t cascadasen-web .
```

These differ from `backend/Dockerfile` and `web/Dockerfile`, which are the local compose images (bind-mounted data, Vite dev server).

## Architecture
```
viewer --HTTPS--> CloudFront (no cache) --HTTP :80--> ALB (public subnets) --> Fargate task (public IP)
                                                                              |- backend :8000
                                                                              '- web :80
```
- Region `us-east-1`, account `402909940511` (enforced by `allowed_account_ids` and by `deploy.sh`).
- VPC `10.0.0.0/16`, two public subnets in two AZs (the ALB needs two), internet gateway, no NAT. The task has a public IP to pull images from ECR.
- One ECS service, one task, 4 vCPU / 8 GB (X86_64) shared by both containers, no per-container limits. No high availability.
- ALB routing: `/api/*`, `/docs`, `/redoc`, `/openapi.json`, `/map` go to the backend. Everything else goes to web. Health checks: `/api/v1/health` (backend), `/healthz` (web).
- Security groups: the ALB accepts traffic only from the CloudFront managed prefix list (`com.amazonaws.global.cloudfront.origin-facing`). The task accepts :80 and :8000 only from the ALB. The test listener :8080 has no ingress rule.
- CloudFront: `redirect-to-https`, cache policy `Managed-CachingDisabled`, origin request policy `Managed-AllViewer`, all methods allowed. It is only a proxy for TLS and, later, the domain.
- An ALB cannot have an Elastic IP. CloudFront points to the stable ALB DNS name (output `alb_dns_name`).
- Data is baked into the backend image (`data/processed` at `/data/processed`). There is no database. Shared sessions and persisted runs live in the S3 bucket `cascadasen-sessions-402909940511` (section "Sessions bucket").
- Logs go to CloudWatch group `/ecs/cascadasen`, 7 days. Terraform state lives in S3 bucket `cascadasen-tfstate-402909940511` (versioned, encrypted, `use_lockfile = true`).

## Sessions bucket
Written in Terraform and validated, **not applied yet**: the apply waits until the user has tested sessions locally (docker compose with the file store).
- `infrastructure/s3.tf`: bucket `cascadasen-sessions-402909940511` (output `sessions_bucket`), all four public access blocks on, SSE-S3 (`AES256`), ownership `BucketOwnerEnforced` (no ACLs).
- Lifecycle: one rule per prefix, `sessions/` (session documents and their runs, `sessions/{sid}.json`, `sessions/{sid}/runs/{rid}.json`) and `runs/` (runs created outside a session). Objects expire after `var.session_ttl_days` (default 1) and incomplete multipart uploads are aborted after 1 day. S3 rounds each expiry up to the next UTC midnight, so an object lives between 24 and 48 hours. The app enforces the 24 h session TTL itself; the lifecycle only cleans up.
- Task role `cascadasen-task` (`infrastructure/iam.tf`, `task_role_arn` in the task definition): `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `sessions/*` and `runs/*`, and `s3:ListBucket` on the bucket. ListBucket has no prefix condition so a missing key answers 404 instead of 403.
- Backend container environment (`infrastructure/ecs.tf`; the web container gets none): `CASCADASEN_SESSION_STORE=s3`, `CASCADASEN_SESSION_BUCKET=<bucket>`, `CASCADASEN_AWS_REGION=<region>`, `CASCADASEN_VERSION=<image tag>`, `CASCADASEN_TRUSTED_PROXY_HOPS=2` (rate limits key on the `X-Forwarded-For` entry CloudFront appended, the second from the right, because the ALB appends CloudFront's address after it; the ALB only accepts CloudFront's origin-facing prefix list). `CASCADASEN_VERSION` is the image tag of the last `terraform apply`, not of the running image: `deploy.yml` copies the current task definition and swaps only the images, so run records (`code_version`) keep the apply-time tag until the next apply. It is informational only.
- `deploy-role-policy.json` adds `cascadasen-task` to `iam:PassRole`, because every revision the GitHub workflow registers now names that role.
Steps after the apply, once:
1. `aws_ecs_service.app` ignores `task_definition`, and the GitHub workflow copies the revision the service currently runs. So the apply registers a new revision (task role and environment) that nothing uses yet. Point the service at it: `aws ecs update-service --cluster cascadasen --service cascadasen --task-definition cascadasen:<revision registered by terraform>`. From then on CI copies the role and the environment.
2. Re-attach the updated `infrastructure/deploy-role-policy.json` to `IAM-Role-ECS-Deploy`; without the new PassRole entry CI fails to register revisions.
## Blue/green
The service uses native ECS blue/green (`deployment_configuration.strategy = "BLUE_GREEN"`, bake time 2 minutes). Each container has its own blue and green target group (4 in total), configured through `advanced_configuration` on each `load_balancer` block. During a deployment ECS starts the new task, registers it in the green target groups behind the test listener (:8080), swaps the production listener rules, waits for the bake time and stops the old task. The forward action of the listener rules is changed by ECS, so Terraform ignores it (`ignore_changes = [action]`).

Terraform validates the two `load_balancer` blocks, but only the ECS API proves at apply time that it accepts two target group pairs. If it rejects them, the fallback is one target group (web) with nginx proxying the backend paths to `127.0.0.1:8000`.

## Deploy
```bash
infrastructure/deploy.sh plan    # account check, state bucket, init, validate, plan
infrastructure/deploy.sh apply   # ECR, build and push images, full apply, prints the URL
```
- Credentials: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from the environment. If unset, the script sources the team keys file. It never prints them and does not use `AWS_PROFILE`.
- Review the plan before `apply`. `apply` aborts when the tree changed since `plan`.
- Image tag: short commit, plus `-dirty-<UTC time>` when `backend`, `web`, `data` or `infrastructure/docker` have uncommitted changes. ECR is immutable and keeps the last 10 images. `apply` skips a build when the tag already exists.
- A new deployment is a new commit and a new tag: the task definition changes and ECS runs the blue/green swap.
- `plan` creates only the state bucket in AWS.

## Domain with Route 53 and ACM
`var.domain_name` (default `sub50.cl`) drives three things:
- `infrastructure/route53.tf`: the hosted zone, plus apex `A` and `AAAA` alias records pointing to the CloudFront distribution. The domain is not registered by this stack.
- `infrastructure/acm.tf`: an ACM certificate for `sub50.cl` and `*.sub50.cl` (us-east-1), validated by the CNAME records `aws_route53_record.acm_validation` in the zone, and `aws_acm_certificate_validation`, which waits until the certificate is ISSUED.
- `infrastructure/cloudfront.tf`: the distribution alias `sub50.cl` and the validated certificate (SNI, TLS 1.2 minimum). The distribution takes the certificate from `aws_acm_certificate_validation`, so it is only updated once the certificate is issued.

NS delegation is a manual step. Read `terraform -chdir=infrastructure output route53_name_servers` and set those four name servers for `sub50.cl` at the .cl registrar (NIC Chile). Validation and the alias only work after delegation; `aws_acm_certificate_validation` times out before that. The site is then at the `site_url` output. The `*.cloudfront.net` URL keeps working.

Optional, in `infrastructure/terraform.tfvars` (git-ignored, example in `terraform.tfvars.example`): `origin_https = true` and `alb_certificate_arn` make the ALB production listener HTTPS :443 and CloudFront use `https-only`. That needs a certificate whose name matches the origin host, so it also needs a record such as `alb.sub50.cl` pointing to the ALB; it is not set up.

## Automatic deploy from GitHub
`.github/workflows/deploy.yml` runs on every push to `main` (and by hand with "Run workflow") and uses only the AWS CLI, no Terraform. Steps: assume the role `arn:aws:iam::402909940511:role/IAM-Role-ECS-Deploy` through GitHub OIDC; build and push the `backend` and `web` images to ECR tagged with the short commit; register a new revision of the `cascadasen` task definition with those images; `aws ecs update-service` and wait for the blue/green deploy to be stable; invalidate CloudFront (`/*`, distribution found by the alias `sub50.cl`). Runs are serialized (`concurrency: deploy`).
The role ARN, registry, cluster, service, and domain are hardcoded in the workflow: the repository variables cannot be edited, and none of them is a secret. The public Mapbox token is read from the default in `deploy.sh` (GitHub push protection rejects the token when it is written in the workflow file).
Infrastructure changes (new resources, sizing, the ECR repositories) are not deployed by the workflow. Apply them by hand with `infrastructure/deploy.sh`. The ECS service has `ignore_changes = [task_definition]`, so a manual `terraform apply` does not roll the service back to an older revision.
Setup in AWS (account 402909940511), done once by hand (already done):
1. IAM OIDC identity provider: URL `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.
2. The role `IAM-Role-ECS-Deploy`, trusted for this repository. The `sub` uses the immutable ID format: `repo:platanus-hack@189188603/platanus-hack-26-cl-team-9@1466159115:*` (organization ID 189188603, repository ID 1466159115). If AssumeRoleWithWebIdentity is denied, GitHub still emits the classic claim: use `repo:platanus-hack/platanus-hack-26-cl-team-9:*` (or `...:ref:refs/heads/main`).
3. The permissions policy in `infrastructure/deploy-role-policy.json`: ECR push on `cascadasen/*`, four ECS actions (describe service and task definition, register task definition, update service), `iam:PassRole` for the three `cascadasen-*` ECS roles (task execution, ECS infrastructure, task), and CloudFront list and invalidate. Attach it to the role.
Pushing `.github/workflows/*` needs a GitHub token with the `workflow` scope (`gh auth refresh -h github.com -s workflow`).
## Mapbox token
The web image needs `VITE_MAPBOX_TOKEN` at build time (Vite inlines it). `deploy.sh` passes it as a build argument. The value is a public `pk.*` token with a default in `deploy.sh`; export `VITE_MAPBOX_TOKEN` to override it.

## Backlog
No issue numbers yet: `scripts/issue.sh` does not exist in the repo and the fork has issues disabled. Create these in the team tracker:
- HTTPS between CloudFront and the ALB: an `alb.sub50.cl` record pointing to the ALB, CloudFront origin set to that name, and `origin_https = true`.
- CloudFront origin secret header, so the ALB rejects requests that do not come from this distribution (the prefix list allows any CloudFront distribution).
- Multi-task high availability.
- Load data from S3 instead of baking it into the image.

Last deploy check: blue/green swap proof (second deploy).
