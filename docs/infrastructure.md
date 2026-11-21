# Infrastructure

AWS deployment of CascadaSEN: one Fargate task behind an ALB and CloudFront, defined in Terraform under `infrastructure/`. This page grows with the Terraform and `deploy.sh` work.

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
