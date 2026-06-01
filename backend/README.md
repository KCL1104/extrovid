# extrovid-backend — Milestone 1

Text-only planning pipeline: **Brief → Script → Visual Brief → Concept Set → Storyboard JSON**, powered by
PydanticAI against Qwen (DashScope), fully mockable with zero network.

## Stack
- FastAPI + PydanticAI (`AlibabaProvider` → DashScope OpenAI-compatible endpoint)
- SQLModel + async SQLAlchemy 2.0; **PostgreSQL** (asyncpg) as the target DB, SQLite as the offline test fallback
- Managed with `uv`

## Quickstart (mocked, no API key, no DB server needed for the pipeline)
```bash
uv sync
cp .env.example .env            # USE_MOCK_LLM=true by default
uv run pytest                   # full offline test suite
uv run uvicorn app.main:app --reload   # open http://127.0.0.1:8000/docs
```

## Running against real services
- Real Qwen: set `USE_MOCK_LLM=false` and `DASHSCOPE_API_KEY=...` in `.env` (no code change).
- PostgreSQL: set `DB_URL=postgresql+asyncpg://user:pass@host:5432/db`, then `uv run alembic upgrade head`.
  A local Postgres can be started with `docker compose up -d` (requires Docker).

## Layout
See `docs/ai-native-director-editor-spec-v2-en.md` and the approved plan. `app/schemas/pipeline.py` holds the
locked pipeline/storyboard schemas; `app/pipeline/orchestrator.py` is the linear Brief→Storyboard chain;
`app/providers/model_factory.py` is the real-vs-mock LLM seam.
