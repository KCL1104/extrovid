# Deploy extrovid to Alibaba Cloud International (Singapore)

Single-VM **ECS + Docker Compose + Caddy**. Images **build on the box** from synced source —
no container registry. CD is a **GitHub Actions rsync-over-SSH** workflow. Rationale and the
deployment-model comparison live in [`../docs/alibaba-cloud-migration.md`](../docs/alibaba-cloud-migration.md).

## Topology
- **ECS** runs `backend` (FastAPI, single instance — the reconciler has no leader election),
  `frontend` (Next.js standalone), and `caddy` (reverse proxy, SSE-safe, optional auto-TLS).
- **ApsaraDB RDS for PostgreSQL** (HA) on the VPC internal endpoint.
- **OSS** bucket (S3-compatible) for generated media, via presigned GET URLs.
- **DashScope** unchanged (already international/Singapore).

## How CD works
Push to `main` (or run the workflow manually) → GitHub Actions:
1. `rsync` the repo to `/opt/extrovid/app/` on the box (excludes `.git`, `node_modules`, `.next`, `deploy/.env`).
2. `ssh` → `cd /opt/extrovid/app/deploy && docker compose up -d --build`.

The box keeps its own `deploy/.env` (gitignored, never synced). Backend runs `alembic upgrade head` on boot.

GitHub secrets: `SSH_HOST`, `SSH_USER`, `SSH_KEY` (+ optional `SSH_PORT`).

## The box `.env`
Lives at `/opt/extrovid/app/deploy/.env` (copied from `.env.example`, filled with the real RDS
endpoint, OSS bucket + app AccessKey, DashScope key, strong `SESSION_SECRET`/`API_TOKEN`).
- `NEXT_PUBLIC_API_BASE` is baked at build time → set it to `http://<EIP>/api` (or `https://<domain>/api`).
- `SITE_ADDRESS=:80` serves plain HTTP; set it to a hostname for Caddy auto-TLS.
- `USE_MOCK_VIDEO=false` **and** a single backend instance — both required together.
- DB over TLS: append `?ssl=require` to `DB_URL` (asyncpg ignores `?sslmode=`).

## Smoke test (all of these — `/health` alone proves nothing)
- `curl http://<EIP>/health` → `{"status":"ok"}`
- Sign in / create a project in the UI.
- Trigger a real generation (`USE_MOCK_VIDEO=false`) → reconciler polls, video ingests (`docker compose logs -f backend`).
- **SSE**: plan stream + director chat + job progress stream live, uncut.
- **Media GET**: open a presigned OSS URL in a fresh tab (no auth) → 200 + bytes; a gallery video plays.

## Manual deploy from the box
`cd /opt/extrovid/app/deploy && docker compose up -d --build`
