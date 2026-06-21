# extrovid → Alibaba Cloud International（Singapore / ap-southeast-1）遷移指南

> **TL;DR — 最終建議：採用「單台 ECS VM + Docker Compose + Caddy（或 nginx）」承載 backend，frontend 同一台 Compose（或可獨立、可水平擴展）。** 理由一句話：本 app 的 backend 帶有一個**永遠常駐、無 leader election、每 N 秒輪詢 RUNNING video job 的 in-process reconciler**，外加多條 **SSE 長連線**，這要求「永遠剛好一個 always-on 實例 + 不緩衝的反向代理 + 長 read timeout」——單台 ECS VM 是唯一能 100% 自己掌控「single-instance 語義 / SSE buffering / 開機 Alembic / COPY 進去的 ffmpeg」且風險最低的形態。SAE（pin min=max=1）是可接受的「免運維」次選；ACK / ACS / FC 對本 app **不建議**（彈性多實例會造成重複輪詢）。

---

## 1. 架構對照表 — Railway → Alibaba Cloud

| 元件 | 目前（Railway） | Alibaba Cloud International（Singapore, ap-southeast-1） | 是否需改程式 |
|---|---|---|---|
| Backend 容器 | Railway 服務（$PORT、HTTPS domain） | **單台 ECS + Docker Compose**（推薦）／ SAE app（min=max=1）／ ACK 單副本 | 否（僅 ENV + 前端 build-arg） |
| Frontend 容器 | Railway 服務（Next.js standalone） | 同一台 Compose 的第二個 service（或獨立 SAE/容器，**可水平擴展**） | **是**：`NEXT_PUBLIC_API_BASE` build-arg + 改 hardcoded fallback |
| PostgreSQL | Railway managed PG（private `DATABASE_URL`） | **ApsaraDB RDS for PostgreSQL**，High-availability `pg.n2.2c.2m`（2c/4GB），PG 16/17，ESSD PL1 20GB，VPC 內網 endpoint | 否（`DATABASE_URL` 換指向；TLS 注意見 §5） |
| 物件儲存 | S3 相容（Tigris bucket） | **OSS**（S3 相容），私有 bucket，`ap-southeast-1` | 1 行：加 `signature_version='s3'`（見 §5） |
| 網域 / TLS | Railway 自動 HTTPS | **ALB HTTPS listener** + Certificate Management Service DV 憑證（或上傳 Let's Encrypt）／ ECS 上 **Caddy 自動 Let's Encrypt** | 否 |
| CI/CD | Railway build & deploy | **ACR**（Container Registry）+ **GitHub Actions**（`aliyun/acr-login`），ECS=`compose pull && up -d` / SAE=`UpdateApplication` | 是：frontend Dockerfile 加 build ARG |
| AI 供應商 | DashScope **國際** endpoint | **完全不變**——`dashscope-intl.aliyuncs.com` 本來就 hosted in Singapore；同區 = 延遲下降 | 否 |

> ICP：Singapore 主機**免 ICP 備案**（備案僅針對 mainland-China 機房）。補充：若對 mainland 用戶提供服務，理論上可能涉及 PSB 公安備案——對國際受眾不適用，非 blocker。

---

## 2. 部署形態比較

| 維度 | **ECS + Docker Compose**（推薦） | **SAE 2.0**（次選） | **ACK / ACS（K8s）**（不建議） |
|---|---|---|---|
| 部署方式 | SSH，`docker compose up -d`，Caddy/nginx 前置 | 容器映像（ACR/公開）直接託管，ALB Ingress | K8s manifest / Deployment + Ingress controller + node pool |
| **常駐 / reconciler 支援** | ✅ 一個容器 = 剛好一個 reconciler，**完全可控** | ⚠️ 設 min=max=1 可達成，但 **rolling deploy 期間可能短暫跑 2 實例 → 重複輪詢**（官方未保證「永遠剛好 1 個」） | ❌ HPA/多副本 = N 個 poller；需 `replicas:1` + `strategy: Recreate` 才安全 |
| **SSE 長連線** | ✅ Caddy/nginx 可關閉 buffering + 長 read timeout，完全自掌 | ⚠️ ALB **原生支援 SSE**（官方明載），但 idle timeout 預設僅 15s，**須手動拉高**、上線前實測不緩衝 | ⚠️ 同 ALB；額外 ingress controller 變數 |
| **Autoscale** | 手動（backend 不該 scale；frontend 可另開實例） | backend **禁用** metric autoscale；frontend 可 scale | 彈性強，但對本 backend 是**危險**（重複輪詢） |
| 運維量 | 中（OS patch / 監控 / 備份 / restart 自理） | **低**（免 OS patch） | **高**（cluster 升級、node pool、ingress） |
| 約略月成本* | ~USD 90–130（VM+EIP+流量，未含 DB/OSS） | backend CU ~USD 42 + ALB ~USD 5–20 | ACK Pro control plane ~USD 72/mo + worker ECS + SLB（**最貴、收益為零**） |

\* 皆為**估算**，Singapore、USD、on-demand；以 buy page 為準。

**對這個 app 的明確建議**：選 **ECS + Docker Compose**。

- reconciler 是 `asyncio.create_task(_reconciler_loop())`，**無 leader election**：任何「可能跑出第 2 個 backend 實例」的形態（SAE autoscale、SAE rolling、ACK HPA、ACS 多 pod、FC provisioned>1）都會**對每個 RUNNING video job 重複輪詢**，造成重複 DashScope poll 成本、job/version 狀態 race、重複 `dispatch_deferred`，且開機 `alembic upgrade head` 在多副本下會**互相 race**。
- scale-to-zero（FC 預設、ACS 彈性）會直接**殺掉 reconciler loop**，導致已提交的 Wan job 永不被輪詢/ingest，continuation chain 卡死。
- ffmpeg encode 需要**真實 CPU + ephemeral disk**，偏好實機而非極小 serverless 實例。
- 結論：單台 ECS VM 一台 = 一個 reconciler、不會 scale-to-zero、CPU 充足、SSE buffering 全可控，**概念風險最低**。若要免運維可退而求其次用 **SAE pin min=max=1（且 backend 絕不開 autoscale）**，但務必在 staging 驗證 SAE 不緩衝 `text/event-stream`、且 rolling deploy 不會雙跑（必要時加 Postgres advisory-lock leader election）。**不要**為兩個 service 上 K8s。

---

## 3. 各元件遷移細節

### 3.1 Compute（ECS 推薦規格）
- 機型：`ecs.g7.large` / `ecs.g8i.large`（2 vCPU/8 GiB）起步；若常做真實 video + ffmpeg encode，升 `.xlarge`（4 vCPU/16 GiB）。
- 步驟：建 VPC（如 `10.0.0.0/16`）+ 兩個 vSwitch 跨 2 個 zone；建 ECS、掛 EIP；裝 Docker + Compose；兩個容器 `restart: always`；前置 Caddy（自動 Let's Encrypt TLS）。
- `CMD` 維持不變：`alembic upgrade head && uvicorn ...`（單實例下安全）。
- 注意映像 CPU arch 與 ECS 一致（x86_64 vs Arm `g8y`）；`mwader/static-ffmpeg` 靜態 binary 直接可用。

### 3.2 ApsaraDB RDS for PostgreSQL
- 規格：**High-availability** `pg.n2.2c.2m`（2 vCPU/4 GB，400 conn），ESSD PL1 20GB，PG **16 或 17**（1-core 級別已停售；RDS Serverless 不支援 PG 18）。
- **與 compute 同一 VPC**，只走**內網 endpoint**（`...pg.rds.aliyuncs.com:5432`），勿開 public endpoint。
- Whitelist：**直接掛 ECS 的 VPC security group** 到 RDS（比逐一列 IP 穩）。預設 RDS 封鎖一切（whitelist=127.0.0.1），忘了加 = 開機 `alembic upgrade head` 會 hang 在連線、uvicorn 起不來。
- 連線池：每副本 `pool_size≈5`，replicas×pool 遠低於 400。
- `_normalize_async_pg()` 會把 `postgresql://` 自動轉成 `postgresql+asyncpg://`，所以 RDS 給的 URL 直接貼即可。
- 物件搬遷（DB 很小，因 media 在 OSS）：
  ```bash
  pg_dump -Fc --no-owner --no-privileges -h <railway-host> -p <port> -U <user> -d <db> -f extrovid.dump
  # 在 VPC 內的 ECS 對 RDS 內網 endpoint 還原（或暫時 whitelist 你的 IP）
  pg_restore --no-owner -j4 -h <rds-internal-endpoint> -p 5432 -U <rds-priv-user> -d <db> extrovid.dump
  ```
  `pg_dump` 主版本須對齊來源（Railway）；RDS 禁止真 SUPERUSER，用 `--no-owner --no-privileges`，role DDL 對映到 `rds_superuser`。還原後跑 `alembic upgrade head` 收斂 schema。

### 3.3 OSS（boto3 相容 / endpoint / region / presigned / CORS / 搬遷）
- **boto3 相容**：OSS 是**真 S3 相容 REST API**。`put_object` / `get_object` / `delete_objects` / `generate_presigned_url` 皆支援。
- **Endpoint / region（已 fact-check 修正）**：用 **`s3.` 前綴**的 S3 相容 endpoint
  - `S3_ENDPOINT=https://s3.oss-ap-southeast-1.aliyuncs.com`
  - `S3_REGION=ap-southeast-1`
  > ⚠️ 研究內另一段曾建議**不含 `s3.` 前綴**的 `https://oss-ap-southeast-1.aliyuncs.com` + 不設 `signature_version` —— 此與官方 AWS-SDK 指南**衝突**。以本節（`s3.`-前綴 + `signature_version='s3'`）為準。
- **Addressing**：`addressing_style='virtual'` **必須保留**（OSS **只接受** virtual-hosted，path-style 被拒）。
- **Presigned GET**：可用（唯讀無 body，避開 SigV4 chunked-encoding 限制）。簽章的 region/endpoint 須對齊 bucket（ap-southeast-1），否則 `403 SignatureDoesNotMatch`。OSS presign 上限 **7 天**（現行 `presign_ttl_sec=3600` OK）。
- **內網 vs 公網 endpoint（進階優化，可選）**：backend 寫入用內網 `oss-ap-southeast-1-internal.aliyuncs.com`（免流量費），但 **presigned URL 必須用公網 endpoint 簽** 否則瀏覽器抓不到——這需要**兩個 client / 覆寫 endpoint**。**第一階段建議只用公網 `s3.`-前綴 endpoint 簡化**，內網優化留待 phase 2。
- **CORS**（bucket 上設，與 FastAPI CORS 是兩回事，兩者都要）：Console → bucket → CORS：AllowedOrigin=前端網域（初期可 `*`）、AllowedMethod=`GET,HEAD`、ExposeHeader=`ETag,Content-Length,Content-Type`、MaxAgeSeconds=86400。
- **RAM 最小權限 AccessKey**（勿用 root）：
  ```json
  {"Version":"1","Statement":[{"Effect":"Allow",
   "Action":["oss:GetObject","oss:PutObject","oss:DeleteObject","oss:ListObjects"],
   "Resource":["acs:oss:*:*:BUCKETNAME","acs:oss:*:*:BUCKETNAME/*"]}]}
  ```
- **物件搬遷（Tigris → OSS，用 rclone；ossutil 不能拉非 OSS 來源）**：
  ```bash
  # rclone 設兩個 remote：tigris(type=s3,provider=Other) / oss(type=s3,provider=Alibaba,
  #   endpoint=oss-ap-southeast-1.aliyuncs.com,region=ap-southeast-1,acl=private)
  rclone copy tigris:SRC_BUCKET oss:DEST_BUCKET -P --transfers=16 --checkers=16
  rclone sync tigris:SRC_BUCKET oss:DEST_BUCKET -P     # 切換前補 delta
  rclone check tigris:SRC_BUCKET oss:DEST_BUCKET       # 驗 count/size
  ```
  **物件 key 必須完全保留**（`project_id/<asset_id>.<ext>`），否則 DB `bucket_key` 解析不到。大量資料可改用 Alibaba **Data Online Migration**（server-side 拉取）。

### 3.4 網路 / 網域 / TLS（確認免 ICP）
- 一個 Singapore VPC，ALB + ECS/SAE backend + RDS + OSS 同區；vSwitch 跨 2 zone HA。
- **Ingress = ALB**（非 CLB）：ALB **原生支援 SSE**（官方 product overview 明載 LLM 推論串流）；HTTPS listener 開 HTTP/2、WebSocket 預設開。
  > ⚠️ ALB 的 idle/request timeout 預設僅 **15s**，**遠不足以撐 SSE**，必須在 listener 拉高。具體「1–600s 範圍 / Quota Center 拉到 3600s / 升級實例才到 900s+」等**精確數值 fact-check 未能逐一證實**——架構結論（預設 15s 太短、必須調高到 ≥600s 理想 900s）成立，請以 console 實際可調值為準並上線前實測串流不被緩衝。
- **Caddy 路線（ECS 推薦）**：對 SSE route 設 `flush` / 關閉 buffering、長 read timeout；自動 Let's Encrypt。nginx 則 `proxy_buffering off;` + `proxy_read_timeout 900s;`。
- **TLS 憑證**：Certificate Management Service 簽 **DV 憑證**部署到 ALB HTTPS listener；或上傳 Let's Encrypt（90 天，ACME 自動續）。
  > ⚠️ 免費 DV 憑證的「每帳號 20 張/有效期」**無法在現行國際文件證實**（confidence: low）——以 console 實際 quota 為準；備案 plan B 用 Let's Encrypt。
- **Cloudflare（若用）**：static frontend 可 orange-cloud 代理；但 **SSE/streaming API 子網域請走 DNS-only（grey-cloud）直連 ALB**，避開 Cloudflare ~100s timeout + buffering 打斷 director-chat/job-progress。

### 3.5 ACR + GitHub Actions CI/CD
- ACR：`ap-southeast-1`，namespace `extrovid`，repo `backend` / `frontend`。**Personal Edition 免費但無 SLA（官方明示「勿用於 production」）**；production 用 **Enterprise Basic**（訂閱，約數十 USD/mo）。從 compute 走 ACR **`-vpc` 內網 endpoint** 拉取免流量費。
  > 註：ECS+Compose 路線可**完全跳過 ACR**，直接在 VM 上 `docker build`，省下 Enterprise 費用。
- GitHub Actions（要點）：
  ```yaml
  - uses: aliyun/acr-login@v1
    with: { login-server: registry-intl.ap-southeast-1.aliyuncs.com, username: ..., password: ... }
  - run: docker build --build-arg NEXT_PUBLIC_API_BASE=https://<backend-domain>/api -t <reg>/extrovid/frontend:${{github.sha}} ./frontend
  - run: docker build -t <reg>/extrovid/backend:${{github.sha}} ./backend
  - run: docker push <reg>/extrovid/frontend:${{github.sha}} && docker push <reg>/extrovid/backend:${{github.sha}}
  # 部署：ECS=ssh 'docker compose pull && up -d' / SAE=aliyun sae UpdateApplication
  ```

### 3.6 DashScope 端點與同區延遲
- **完全不動**：`DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1` + 現有 **Singapore 國際 key**（key 是 region-bound，但你留在同 region+account）。`dashscope-intl` 本來就 hosted in Singapore，compute 搬到 ap-southeast-1 = submit→poll 迴圈延遲大降，**零供應商/key 變更**（最高槓桿、最低風險）。
- video async 契約：submit 帶 `X-DashScope-Async: enable` → 回 `task_id` → poll `GET /api/v1/tasks/{id}`；result URL + task_id **24h 後失效**，故「下載→re-upload 到自家 OSS」是必要 pattern，reconciler 須在 24h 內完成。
- Wan 速率限制是 **account 級**（submit RPS + 並行任務上限，跨所有 key/RAM user/workspace 共享）；**單一 always-on poller** 正好符合，多副本會壓爆共享配額。poll 維持 ~15s 間隔。
- **PrivateLink（phase-2 可選優化）**：`com.aliyuncs.dashscope` 在 Singapore 可用（US Virginia 不支援）；要改 `DASHSCOPE_BASE_URL` 的 host 到 private 域（預設 endpoint 為 **HTTP-only**，要 TLS 用 custom domain `vpc-ap-southeast-1.dashscope.aliyuncs.com`）。把 chatty 的 JSON submit/poll 走私網。**非 cutover blocker**。
  > 註：result video bytes 來自 Alibaba 自家 `dashscope-result-*` bucket 走 `oss-accelerate`，**不在你的 region/帳號**；同區只省延遲不省下載 class。「該下載完全免費計給 Alibaba」是合理推論但**非官方計費保證**——惟你 ECS 的 inbound 本就免費，實務影響低。真正免費的是「re-upload 到自家同區 OSS 內網」這一段。

---

## 4. 程式與設定變更

### 4.1 ENV 變數對照表（Railway → Alibaba）

| ENV | Railway（現） | Alibaba（新） | 備註 |
|---|---|---|---|
| `DB_URL` / `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | `postgresql+asyncpg://<user>:<pw>@<rds-internal>:5432/<db>` | TLS 用 `?ssl=require`（**非** `?sslmode=`）；`AUTO_CREATE_DB=false` |
| `S3_ENDPOINT` | `https://<bkt>.s3.tigris.dev` | `https://s3.oss-ap-southeast-1.aliyuncs.com` | **含 `s3.` 前綴** |
| `S3_REGION` | `auto` | `ap-southeast-1` | 顯式設，否則 presign 簽章可能不符 |
| `S3_BUCKET` | `<tigris-bucket>` | `<oss-bucket>`（私有，ap-southeast-1） | 全球唯一名 |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | Tigris keys | RAM user AK/SK（限該 bucket） | 勿用 root |
| `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` | 國際 key / `dashscope-intl...` | **不變** | — |
| `USE_MOCK_LLM/IMAGE/VIDEO` | （多為 mock） | `false`（**`USE_MOCK_VIDEO=false` 才會啟動 reconciler**） | `USE_MOCK_TTS` 暫留 `true` 直到驗證 qwen3-tts |
| `SESSION_SECRET` | — | **強隨機值**（現預設 `dev-insecure-change-me` 不可上 prod） | OAuth state 簽章 |
| `API_TOKEN` / 各 daily cap | 沿用 | 沿用 | — |
| `BACKEND_BASE_URL` / `FRONTEND_BASE_URL` | Railway 網域 | 新 Alibaba 網域 | **僅** Google OAuth 啟用時必改；並到 Google Cloud console 加新 redirect_uri |
| `NEXT_PUBLIC_API_BASE`（frontend） | Railway fallback | `https://<backend-domain>/api`（**build-arg**） | 見下 |

### 4.2 需要改的程式
1. **Frontend `NEXT_PUBLIC_API_BASE`（build-time，必改）**：`frontend/lib/api.ts:8` 有 hardcoded Railway fallback；`NEXT_PUBLIC_*` 在 `npm run build` 時就被烤進 bundle，**runtime env 無效**。目前 `frontend/Dockerfile` **沒有對應 build ARG**。
   - 在 `RUN npm run build` **之前**加：`ARG NEXT_PUBLIC_API_BASE` + `ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE`，並用 `--build-arg NEXT_PUBLIC_API_BASE=https://<backend-domain>/api` build；
   - 同時把 `api.ts` 的 hardcoded fallback 改成新網域（保險）。值要含尾段 `/api`。`googleLoginUrl()` 與 gallery video URL 由 `API_BASE` 衍生，會自動跟。
2. **S3 client 確認為 env-only + 加 `signature_version`（1 行，建議）**：`backend/app/services/asset_service.py` 的 `_s3_client()` 目前**沒設 `signature_version`**，依官方 AWS-SDK 指南改為：
   ```python
   Config(signature_version='s3', s3={'addressing_style': 'virtual'})
   ```
   原因：boto3 SigV4 綁 chunked encoding，OSS 上傳會失敗；不設則跨 botocore 版本行為不定，易 `SignatureDoesNotMatch`。若 pinned botocore 已移除 SigV2（`'s3'`），fallback `'s3v4'`（presigned GET 唯讀仍可）。**上線前用 image 內 pinned 版本實測** put + presigned GET + delete。
3. **DB SSL（若 RDS 強制 TLS）**：asyncpg **不認** libpq 的 `?sslmode=`（SQLAlchemy #6275 會**靜默忽略**，給你假的安全感）。兩條路：
   - (A) **最簡**：RDS SSL 關閉，靠 VPC 內網隔離 + whitelist（同區私網常見）；或
   - (B) 啟用 SSL，在 `backend/app/core/db.py` **和** `backend/migrations/env.py` **兩處**都加 `connect_args={'ssl': ssl_ctx}`（否則開機 `alembic upgrade head` 連不上）。或最輕量在 URL 加 `?ssl=require`（asyncpg dialect 認得）。
4. **SSE 反向代理 no-buffering**：程式端已硬化（三個 SSE endpoint 都送 `X-Accel-Buffering: no` + `Cache-Control: no-cache`）。**只需**讓 ALB/Caddy/nginx 不緩衝 `text/event-stream` + read timeout ≥600s（理想 900s）。frontend 用 fetch-based SSE（要送 Bearer header），代理須容忍長連線。
5. **CORS**：FastAPI `allow_origins=['*']`（Bearer token、無 cookie），網域變更**不需動**；OSS bucket CORS 另設（見 §3.3）。可選擇上線後收斂為指定前端 origin。

---

## 5. 切換 Runbook（最小停機）

> 前提：media 在 OSS、DB 僅 metadata，故 DB dump 很小、停機僅數分鐘。

1. **預備（不影響線上）**
   - 建 VPC + 2 vSwitch；建 ECS（裝 Docker/Compose/Caddy）；建 RDS（HA `pg.n2.2c.2m`，PG16/17，內網 endpoint，掛 ECS security group 到 whitelist）；建私有 OSS bucket + RAM AK/SK + bucket CORS；（選）建 ACR repo。
2. **建映像**
   - backend 照原 Dockerfile build。
   - frontend 加 build ARG，`docker build --build-arg NEXT_PUBLIC_API_BASE=https://<backend-domain>/api ...`。
   - push 到 ACR（或直接在 ECS build）。
3. **資料搬遷（bulk）**
   - `pg_dump -Fc --no-owner --no-privileges`（Railway）→ `pg_restore --no-owner -j4` 進 RDS 內網 → `alembic upgrade head`。
   - `rclone copy` Tigris → OSS（保留 key），`rclone check` 驗 count/size。
4. **凍結窗口（最小停機開始）**
   - 將 Railway app 設唯讀或暫停寫入（避免新資料）。
   - `pg_dump` 增量 / 重跑短 dump 補 delta；`rclone sync` 補 OSS delta。
5. **部署順序**
   - 先起 **backend**（ECS `docker compose up -d` 或 SAE `UpdateApplication`）；開機自動 `alembic upgrade head`。
   - 設 ALB HTTPS listener（或 Caddy）、拉高 SSE timeout、綁網域憑證。
   - 再起 **frontend**（已烤入新 API base）。
6. **煙霧測試清單（務必逐項）**
   - `GET /health` → `{status: ok}`。
   - 登入 / 建立專案。
   - 觸發一次真實生成（`USE_MOCK_VIDEO=false`）→ 確認 reconciler 有輪詢、video ingest 成功。
   - **SSE**：plan stream / director chat / job progress 三條都連得上且**不被緩衝**、長連線不中斷。
   - **presigned media GET**：用瀏覽器（無 auth）實際抓一個 presigned OSS URL → 200 + bytes 正確（**不要只測 /health**）；gallery 302 redirect 影片可播。
   - `delete_objects` 批次刪可用。
7. **DNS 切換**
   - 把正式網域 CNAME/A 指向 ALB（或 ECS EIP）。streaming 子網域若經 Cloudflare 改 **DNS-only**。
8. **觀察 + Railway 下線**
   - 觀察 24–48h（涵蓋 reconciler、SSE、egress）。穩定後再**下線 Railway**（停服務、保留備份一段時間）。
9. **Rollback 註記**
   - DNS 可快速切回 Railway（保留 Railway app + 舊 DB 至確認穩定）。
   - 因 cutover 後 OSS/RDS 有新寫入，回退會遺失切換後資料——故 rollback 僅在「切換後短時間內、且能接受少量資料回捲」時使用；超過觀察窗口應以 fix-forward 為主。

---

## 6. 約略成本估算（小型 production，**皆為估算**）

| 項目 | 規格 | 約略月成本（USD） | 信心 |
|---|---|---|---|
| ECS（推薦路線） | 2 vCPU/8 GiB（g7/g8i.large）on-demand | ~65–75（1年訂閱省 30–40%） | 第三方聚合，**未經官方 buy page 證實** |
| EIP + 流量 | 保留 ~$4.4 + egress ~$0.081/GB（或 5Mbps 包頻 ~$17） | ~10–30 | 與 OSS egress 一致 |
| RDS PostgreSQL | HA `pg.n2.2c.2m` + 20GB ESSD PL1 | ~80–130（訂閱；PAYG 高 ~30–40%） | buy page JS-render，**未證實** |
| OSS | Standard ~$0.016/GB-mo + egress 首 100GB 免、後 ~$0.08/GB | 視流量（200GB 存 + 1TB 影片 ≈ ~75） | egress 為主要變動成本 |
| ACR | Personal 免費（dev）／Enterprise Basic（prod） | 0 ~ 數十 | ECS 路線可跳過 |
| ALB（若用 SAE/ALB 路線） | Basic 實例 + LCU | ~5–25 | — |
| **ECS 路線 all-in（含 RDS+OSS）** | | **~USD 160–280**（未含 AI 推論 + 大量 egress） | 估算 |

> SAE 路線：backend CU ~USD 42 + ALB ~5–20 + RDS + OSS，常落在 ~USD 130–220。所有數字以 **Singapore buy page / 計算器（June 2026）** 為準。

---

## 7. 風險與待確認（fact-check 標記）

**已 fact-check CORRECTED（已反映於本文）**
- **OSS endpoint 內部矛盾**：研究中一段曾建議**無 `s3.` 前綴** + 不設 `signature_version` → 與官方 AWS-SDK 指南**衝突**。本文採用 **`s3.oss-ap-southeast-1.aliyuncs.com` + `signature_version='s3'`**。
- **ICP**：免 ICP 確認；但**補充** PSB 公安備案在「服務 mainland 用戶」時可能適用（對國際受眾 moot，非 blocker）。
- **ALB SSE**：官方 product overview 確認原生支援 SSE；但該頁**未**提 HTTP/2、WebSocket、timeout——這些在別的文件，原研究單一引用不夠精確（本文已分開陳述）。

**UNVERIFIABLE / 低信心（不可當事實宣稱）**
- **「SAE min=max=1 永遠剛好 1 個實例」未能證實**：rolling deploy 可能短暫雙跑 → 對 no-leader-election reconciler 會重複輪詢。**故無論如何建議加 leader election，或直接用 ECS 單機。**
- **ALB 精確 timeout 數值**（1–600s 範圍、3600s via Quota Center、quota 名稱、升級實例才到 900s）**未證實**——但「預設 15s 太短、必須調高」結論成立。
- **所有 ECS / EIP / RDS 美元金額**來自第三方聚合或 JS-render buy page，**未經官方 ap-southeast-1 buy page 證實**——務必上線前在計算器確認。
- **PrivateLink 精確每-zone/每-GB 計費**未證實（~$0.01/hr/zone + ~$0.01/GB 為常見模型，方向正確）。
- **DashScope result 影片下載「完全免費計給 Alibaba」**為合理推論、**非官方計費保證**；惟 ECS inbound 本就免費，實務影響低。
- **免費 DV 憑證 quota/有效期**未能在現行國際文件證實——以 console 為準，plan B 用 Let's Encrypt。

**本 app 特定風險**
- **reconciler 無 leader election**：任何能跑出 2+ backend 實例的形態都會重複輪詢、狀態 race、重複 `dispatch_deferred`、開機 Alembic race。**硬 pin 單實例**（只 frontend 可水平擴展）。
- **scale-to-zero 殺 reconciler**：FC/ACS 彈性會凍結 idle 實例 → loop 停 → job 永不 ingest。必須 always-on。
- **`USE_MOCK_VIDEO` 陷阱**：留 `true` 看似正常但永不產真實影片；翻成 `false` 又在多實例下引入重複輪詢——只有「單實例 + `false`」是正解。
- **`NEXT_PUBLIC_API_BASE` build-time 烤入**：忘了 build-arg/改 fallback 會把舊 Railway URL 洩漏給 client。
- **asyncpg 忽略 `?sslmode=`**：用 `?ssl=require` 或 `connect_args`，且 `db.py` 與 `migrations/env.py` 兩處一致。
- **presigned region/endpoint 不符 = 403**；bucket 誤建 public 或錯區 → 即使 `/health` 過、影片播放仍壞。
- **OSS key 必須完全保留**（`project_id/<asset_id>.<ext>`），否則 DB `bucket_key` 解析失敗。
- **ffmpeg encode 需真 CPU + ephemeral disk**：勿用過小 serverless，否則 rough-cut OOM/timeout。
- **24h result URL 失效**：reconciler 須在窗口內完成 download + re-upload，否則資產不可復原、需重新計費生成。
- **`SESSION_SECRET` 預設不安全**：上 prod 前換強值。
