# Infrastructure

AWS deployment of CascadaSEN: one Fargate task behind an ALB and CloudFront, defined in Terraform under `infrastructure/`.

## Images

Both images are built from the repo root with their own Dockerfile and per-Dockerfile ignore file (`<name>.Dockerfile.dockerignore`), for `linux/amd64`.

| Image | Dockerfile | Stack | Port | Health path |
|---|---|---|---|---|
| backend | `infrastructure/docker/backend.Dockerfile` | Python 3.12 + uv, `cascadasen-api`, `data/processed` baked in at `/data` (`CASCADASEN_DATA_DIR=/data`) | 8000 | `/api/v1/health` |
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
- One ECS service, one task, 2 vCPU / 4 GB (X86_64) shared by both containers, no per-container limits. No high availability.
- ALB routing: `/api/*`, `/docs`, `/redoc`, `/openapi.json`, `/map` go to the backend. Everything else goes to web. Health checks: `/api/v1/health` (backend), `/healthz` (web).
- Security groups: the ALB accepts traffic only from the CloudFront managed prefix list (`com.amazonaws.global.cloudfront.origin-facing`). The task accepts :80 and :8000 only from the ALB. The test listener :8080 has no ingress rule.
- CloudFront: `redirect-to-https`, cache policy `Managed-CachingDisabled`, origin request policy `Managed-AllViewer`, all methods allowed. It is only a proxy for TLS and, later, the domain.
- An ALB cannot have an Elastic IP. CloudFront points to the stable ALB DNS name (output `alb_dns_name`).
- Data is baked into the backend image (`data/processed` at `/data`). There is no database and no S3 data.
- Logs go to CloudWatch group `/ecs/cascadasen`, 7 days. Terraform state lives in S3 bucket `cascadasen-tfstate-402909940511` (versioned, encrypted, `use_lockfile = true`).

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

## Backlog
No issue numbers yet: `scripts/issue.sh` does not exist in the repo and the fork has issues disabled. Create these in the team tracker:
- HTTPS between CloudFront and the ALB: an `alb.sub50.cl` record pointing to the ALB, CloudFront origin set to that name, and `origin_https = true`.
- CloudFront origin secret header, so the ALB rejects requests that do not come from this distribution (the prefix list allows any CloudFront distribution).
- Multi-task high availability.
- Load data from S3 instead of baking it into the image.

Last deploy check: blue/green swap proof (second deploy).
