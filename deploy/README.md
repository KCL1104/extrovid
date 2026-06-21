# Deploy extrovid to Alibaba Cloud International (Singapore)

Single-VM **ECS + Docker Compose + Caddy** stack, with **GitHub Actions** CI/CD pushing to **ACR**.
Rationale, comparison vs SAE/ACK, and the full risk list live in
[`../docs/alibaba-cloud-migration.md`](../docs/alibaba-cloud-migration.md). This file is the
do-it checklist.

> What's already in the repo (done): `frontend/Dockerfile` build-arg, configurable
> `S3_SIGNATURE_VERSION`, `docker-compose.yml`, `Caddyfile`, `.env.example`, the CI workflow.
> What you do below needs your Alibaba account, money, and credentials — it can't be scripted for you.

---

## 0. One decision before you start
Pick a domain you control (e.g. `app.example.com`). Both the frontend and the API are served from
it (`/api/*` → backend, everything else → frontend), so you need **one** domain and **one** cert.

---

## 1. Provision (Alibaba Cloud console, Singapore / `ap-southeast-1`)

| # | Resource | Notes |
|---|---|---|
| 1 | **VPC** + 2 vSwitches (2 zones) | e.g. `10.0.0.0/16`. Everything below goes in here. |
| 2 | **ECS** instance | `ecs.g7.large`/`g8i.large` (2c/8G) to start; `.xlarge` if heavy real video. Ubuntu 22.04. Attach an **EIP**. |
| 3 | **Security group** | Inbound: `80`, `443` from `0.0.0.0/0`; `22` from your IP only. |
| 4 | **ApsaraDB RDS for PostgreSQL** | HA `pg.n2.2c.2m`, PG 16/17, ESSD PL1 20GB. **Same VPC, internal endpoint only.** Whitelist: add the **ECS security group** (not IPs). Create DB `extrovid` + a non-super user. |
| 5 | **OSS bucket** | `ap-southeast-1`, **private**. Set bucket **CORS**: AllowedOrigin = your domain (or `*` to start), Methods `GET,HEAD`, ExposeHeader `ETag,Content-Length,Content-Type`, MaxAge `86400`. |
| 6 | **RAM user** + AccessKey | Least-privilege policy on the one bucket (see migration doc §3.3). Use this AK/SK, **never the root key**. |
| 7 | **ACR** (Container Registry) | Namespace `extrovid`, repos `backend` + `frontend`, `ap-southeast-1`. Set the registry password. Personal edition is free (no SLA); Enterprise for real prod. |
| 8 | **DNS** | A record `app.example.com` → the ECS EIP. (If Cloudflare: keep this record **DNS-only / grey-cloud** so SSE isn't buffered/timed-out.) |

---

## 2. One-time ECS box setup
SSH in, then:
```bash
# Docker + compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # re-login after this

# App dir + config
sudo mkdir -p /opt/extrovid && sudo chown $USER /opt/extrovid
cd /opt/extrovid
# copy these two from the repo's deploy/ folder:
#   docker-compose.yml, Caddyfile
cp /path/to/repo/deploy/docker-compose.yml .
cp /path/to/repo/deploy/Caddyfile .
cp /path/to/repo/deploy/.env.example .env
$EDITOR .env                    # fill in everything (DB_URL, OSS, DASHSCOPE, SESSION_SECRET, DOMAIN, REGISTRY…)

# Log in to ACR so `docker compose pull` works (use the -vpc host = free in-region pulls)
docker login registry-intl-vpc.ap-southeast-1.aliyuncs.com
```
Generate a strong `SESSION_SECRET` and `API_TOKEN`: `openssl rand -hex 32`.

---

## 3. GitHub secrets
Repo → Settings → Secrets and variables → Actions → **New repository secret**, add all from the
header of [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml):
`ACR_REGISTRY` (internet host `registry-intl.ap-southeast-1.aliyuncs.com`), `ACR_NAMESPACE`,
`ACR_USERNAME`, `ACR_PASSWORD`, `NEXT_PUBLIC_API_BASE` (`https://app.example.com/api`),
`SSH_HOST`, `SSH_USER`, `SSH_KEY`, optionally `SSH_PORT`, `DEPLOY_PATH`.

> The frontend bundle bakes `NEXT_PUBLIC_API_BASE` at build time — get it right here or the
> client calls the wrong backend.

---

## 4. Migrate the data
DB is small (media lives in OSS), so this is quick. From a machine with both endpoints reachable
(do the restore from inside the VPC, e.g. the ECS box):
```bash
# Postgres: dump from Railway, restore into RDS
pg_dump -Fc --no-owner --no-privileges -h <railway-host> -p <port> -U <user> -d <db> -f extrovid.dump
pg_restore --no-owner -j4 -h <rds-internal-endpoint> -p 5432 -U <rds-user> -d extrovid extrovid.dump
# (pg_dump major version must match the Railway server's)

# Objects: Tigris → OSS, KEYS PRESERVED (project_id/<asset_id>.<ext>)
rclone copy  tigris:SRC_BUCKET oss:DEST_BUCKET -P --transfers=16 --checkers=16
rclone check tigris:SRC_BUCKET oss:DEST_BUCKET     # verify count/size
```
rclone remotes: `tigris` = `type=s3, provider=Other, endpoint=<tigris>`; `oss` =
`type=s3, provider=Alibaba, endpoint=oss-ap-southeast-1.aliyuncs.com, region=ap-southeast-1, acl=private`.

---

## 5. First deploy
Push to `main` (or run the workflow manually). CI builds → pushes to ACR → SSH pull & `up -d`.
The backend container runs `alembic upgrade head` on boot. First TLS handshake may take ~30s while
Caddy gets the Let's Encrypt cert.

To deploy by hand from the box instead (uses `TAG` from `.env`):
`docker compose pull && docker compose up -d`.

---

## 6. Smoke test (do all of these — `/health` alone proves nothing)
- `curl https://app.example.com/health` → `{"status":"ok"}`
- Sign in / create a project in the UI.
- Trigger a **real** generation (`USE_MOCK_VIDEO=false`) → confirm the reconciler polls and the
  finished video gets ingested. `docker compose logs -f backend` to watch.
- **SSE**: plan stream + director chat + job progress all connect, stream live, and don't get cut.
- **Media GET**: open a presigned OSS URL in a fresh browser tab (no auth) → 200 + correct bytes;
  a gallery video plays.

---

## 7. Cutover & decommission
1. Point DNS at the ECS EIP (already done in step 1.8 if you set it early).
2. Watch 24–48h (covers the reconciler, SSE, egress).
3. Then stop the Railway services. Keep the Railway DB backup around for a while.

**Rollback:** flip DNS back to Railway (keep it alive until you're confident). Note that writes
made after cutover live only in RDS/OSS, so rollback loses post-cutover data — use it only shortly
after switching; otherwise fix forward.

---

## Gotchas (the ones that bite)
- `USE_MOCK_VIDEO=false` **and** a single backend instance — both required, together. Two instances
  double-poll (no leader election); mock=true never makes real video.
- DB over TLS: append `?ssl=require` to `DB_URL` (asyncpg ignores `?sslmode=`). Or leave SSL off and
  rely on VPC + whitelist.
- OSS object keys must be preserved exactly, or the DB's `bucket_key` won't resolve.
- Don't make the bucket public or put it in the wrong region — presigned GET breaks with a 403 even
  though `/health` is fine.
