# extrovid

**An AI-native director / editor — go from a one-line idea to an edited video.**

extrovid turns a natural-language prompt into a finished short: it writes the brief and
script, extracts a consistent cast, develops the look, builds a storyboard, generates each
shot, adds voiceover, and assembles a rough cut — with a director you can talk to and
natural-language revision at every step. The interface is a **director's studio at golden
hour**: dark, cinematic, calm, precise.

It is designed for **one-prompt-to-video with optional director controls**: the machine owns
the creative and quality-control work; the human supplies the idea, presses a few "start"
buttons, and decides when to publish.

---

## How it works — the pipeline

```
 idea (raw_prompt)
      │  ┌─ (optional) Clarify Q&A — director asks up to 4 questions
      ▼  ▼
   Brief ─▶ Script ─▶ Cast ─▶ Look-dev ─▶ Storyboard      ← planning (one /run call)
                       │         │            │
                  portraits  concept imgs  keyframes        ← image generation
                                              │
                                              ▼
                              Shots (best-of-N, t2v / i2v / r2v)  ← video generation
                                  └─ AI "dailies" review auto-selects the winner
                                              │
                              Voiceover (TTS) ─┤
                                              ▼
                                   Rough cut (ffmpeg: captions + ducked music + VO)
                                              │
                                              ▼
                                    Publish to public gallery
```

The pipeline is a **per-stage state machine** — each stage is its own endpoint and stops until
triggered. In practice the irreducible human inputs are: sign in → create a project → write the
prompt → trigger planning (`/run`) → trigger generation → trigger assembly → (optionally) publish.
Everything else — LLM planning, cast extraction, best-of-N + AI review selection, keyframe-first
continuity chaining, cut assembly, TTS, mixing — runs unattended. Revise / refine / retry /
reorder / trim / pick-a-different-take are **optional** correction levers, available through the
panels or the **Director chat**.

---

## Models & providers

Every model call goes through a **provider seam** gated by a `USE_MOCK_*` flag — all four default
to a deterministic offline mock, so the whole pipeline runs locally with no keys or cost. Flip a
flag to `false` to hit the real provider. Production runs all four real, on Alibaba DashScope /
Qwen Cloud.

| Stage | Real model | Seam |
|---|---|---|
| Script writing | `qwen3.7-max` (flagship) | `app/providers/model_factory.py` |
| Other agents (brief / cast / look-dev / storyboard / clarify / revise / director / import / review) | `qwen3.7-plus` | same |
| Image generation (concept frames / keyframes / portraits) | `wan2.7-image-pro` (up to 4K) | `app/providers/image_factory.py` |
| Image refine / edit | `qwen-image-edit-plus` | same |
| Text-to-speech (voiceover) | `qwen3-tts` | `app/providers/audio_factory.py` |
| Video (t2v / i2v / r2v / video-edit) | **HappyHorse-1.0** (default) or Wan 2.7 | `app/providers/video_factory.py` |

The **video provider** is selectable with `VIDEO_PROVIDER` (`happyhorse` default, or `wan`). Both
ride the same DashScope `video-synthesis` async submit→poll transport and the same
`DASHSCOPE_API_KEY`; the flag only picks model ids. HappyHorse-1.0 ranks #1 on the Artificial
Analysis Video Arena and offers t2v / i2v / r2v / video-edit parity.

See [`docs/model-upgrades-2026-06.md`](docs/model-upgrades-2026-06.md) for the model research and
decisions.

---

## Architecture

**Backend** — Python 3.12+, [FastAPI](https://fastapi.tiangolo.com/) +
[PydanticAI](https://ai.pydantic.dev/) agents, SQLModel / SQLAlchemy 2.0 (async) on PostgreSQL,
Alembic migrations. Generated media lands in S3-compatible object storage (Railway / Tigris),
served via presigned GET URLs. Rough cuts are assembled with the bundled `imageio-ffmpeg` binary.
Multi-user auth (opaque per-user tokens, optional Google OAuth, an admin master token) with
per-user daily caps as a cost guardrail. Long-running video jobs are tracked async (submit → poll)
by a background reconciler, with live progress streamed over SSE.

**Frontend** — Next.js 16 / React 19 / TypeScript, Tailwind (golden-hour design tokens, dark-only),
a 3-pane workstation (plan · board · inspector) plus Cast / Director / Cut panels, fed by the same
SSE stream.

```
backend/
  app/
    agents/      PydanticAI agents (brief, script, cast, storyboard, director, review, …)
    pipeline/    orchestrator — runs the planning stages
    api/         FastAPI routers (projects, pipeline, generation, storyboard, cast, director, roughcut, auth, gallery)
    services/    business logic (planning, generation, review, rough cut, audio, memory, …)
    providers/   model seams (LLM / image / video / audio) — mock ↔ real
    models/      SQLModel DB entities
    schemas/     Pydantic request/response + pipeline contracts
    core/        config, auth, db, http retry, rate limit, event bus
  migrations/    Alembic
  tests/         pytest (≈236 tests)
frontend/
  app/           Next.js routes (projects, gallery, auth)
  components/    workspace UI (Workspace, PlanPanel, ShotInspector, CutPlanner, DirectorPanel, …)
  lib/           API client
docs/            design spec + model/ffmpeg research
brand.md         palette, typography, voice
```

---

## Getting started (local)

Prerequisites: Python 3.12+ with [`uv`](https://docs.astral.sh/uv/), Node 20+, and (optionally) a
PostgreSQL database. With the default mock flags you need **no API keys and no external services**.

### Backend

```bash
cd backend
uv sync
cp .env.example .env          # defaults are all-mock; edit to go real
uv run alembic upgrade head   # set DB_URL first (or use the provided Postgres URL)
uv run uvicorn app.main:app --reload
# → http://localhost:8000  (health: GET /health,  docs: GET /docs)
```

To run against **real** providers, set the relevant `USE_MOCK_*=false`, add `DASHSCOPE_API_KEY`,
and configure the `S3_*` bucket. Optional: `VIDEO_PROVIDER=wan` to use Wan instead of HappyHorse.

### Frontend

```bash
cd frontend
npm install
npm run dev                   # → http://localhost:3000
```

Point it at the backend with `NEXT_PUBLIC_API_BASE` (defaults to the production backend in
`lib/api.ts`).

### Configuration

All settings are env-driven ([`backend/.env.example`](backend/.env.example) lists them). Highlights:

| Var | Meaning |
|---|---|
| `USE_MOCK_LLM` / `USE_MOCK_IMAGE` / `USE_MOCK_VIDEO` / `USE_MOCK_TTS` | mock ↔ real per provider (default `true`) |
| `DASHSCOPE_API_KEY` | Alibaba DashScope / Qwen Cloud key (real mode) |
| `QWEN_MODEL` | non-script agent model (default `qwen3.7-plus`) |
| `QWEN_IMAGE_MODEL` | image-gen model (default `wan2.7-image-pro`) |
| `VIDEO_PROVIDER` | `happyhorse` (default) or `wan` |
| `DB_URL` | PostgreSQL URL (scheme normalized to asyncpg; SQLite fallback for quick local runs) |
| `S3_*` | object storage for generated media |
| `API_TOKEN` / `SESSION_SECRET` / `GOOGLE_CLIENT_ID/SECRET` | auth |
| `DEFAULT_DAILY_VIDEO_CAP` / `DEFAULT_DAILY_IMAGE_CAP` | per-user cost guardrails |

---

## Testing

```bash
cd backend
uv run pytest                 # ≈236 tests; LLM/image/video/audio are mocked
```

If `TEST_DATABASE_URL` is unset, the suite uses an isolated in-memory SQLite database, so it runs
fully offline. Lint with `uv run ruff check`.

---

## Deployment

Both services deploy to **Railway** from their Dockerfiles (CLI-only):

```bash
railway up --service backend     # backend/Dockerfile: alembic upgrade head → uvicorn
railway up --service frontend    # frontend/Dockerfile: Next.js standalone
```

The backend container runs migrations on boot. Build config is pinned to
`builder=DOCKERFILE`, `rootDirectory=backend|frontend`. Run one deploy at a time and watch it land.

---

## License

[MIT](LICENSE) © 2026 extrovid — use it for anything, just keep the copyright notice.
