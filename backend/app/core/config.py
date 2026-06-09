"""Application settings (pydantic-settings, .env-driven)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_async_pg(url: str) -> str:
    """Coerce a plain Postgres URL to the asyncpg driver SQLAlchemy expects.

    Railway exposes ``postgresql://...``; some providers use ``postgres://...``. SQLAlchemy's
    async engine needs ``postgresql+asyncpg://...``. SQLite and already-qualified URLs pass through.
    """
    if url.startswith("postgresql+asyncpg://") or url.startswith("sqlite"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    use_mock_llm: bool = True
    dashscope_api_key: str | None = None
    qwen_model: str = "qwen3.6-plus"  # balanced default per docs.qwencloud.com model-selection
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    llm_retries: int = 2

    # --- Image generation (Qwen-Image, DashScope-native sync endpoint) ---
    use_mock_image: bool = True  # mock generator + in-memory storage (offline/free)
    qwen_image_model: str = "qwen-image-plus"  # cheap; qwen-image-2.0-pro for higher quality
    qwen_image_edit_model: str = "qwen-image-edit-plus"  # iterative look-frame refinement
    dashscope_image_url: str = (
        "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )

    # --- AI review (ReviewAgent: scores every finished take against acceptance rules) ---
    auto_review: bool = True  # run the review automatically when a take's video lands
    review_vision: bool = True  # attach the take's poster frame (real-LLM mode only)

    # --- Video generation (Wan, DashScope-native ASYNC: submit -> poll) ---
    use_mock_video: bool = True
    wan_t2v_model: str = "wan2.7-t2v"
    wan_i2v_model: str = "wan2.7-i2v"
    wan_r2v_model: str = "wan2.7-r2v"
    wan_videoedit_model: str = "wan2.7-videoedit"
    dashscope_video_url: str = (
        "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
    )
    dashscope_task_url: str = "https://dashscope-intl.aliyuncs.com/api/v1/tasks"
    video_resolution: str = "720P"
    video_reconcile_interval_sec: int = 10
    video_job_timeout_sec: int = 600  # stuck RUNNING jobs older than this -> FAILED

    # --- HTTP resilience (provider 429/5xx retry with backoff) ---
    http_max_retries: int = 3
    http_retry_base_sec: float = 1.0

    # --- Object storage (Railway / Tigris S3-compatible) ---
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    presign_ttl_sec: int = 3600

    # --- Database (PostgreSQL target; sqlite fallback only when nothing is configured) ---
    db_url: str = "sqlite+aiosqlite:///./dev.db"
    test_database_url: str | None = None
    # When true, the app create_all()s tables on startup (handy for local/dev without Alembic).
    # Keep false in production where Alembic owns the schema. Railway sets AUTO_CREATE_DB=false.
    auto_create_db: bool = False

    app_env: str = "local"

    # --- Auth ---
    # api_token = the admin master token: unlimited, sees all projects. Per-user accounts
    # carry their own opaque tokens + caps. (Unset api_token only disables the admin path;
    # /api still requires a valid per-user token.)
    api_token: str | None = None
    session_secret: str = "dev-insecure-change-me"  # SessionMiddleware (OAuth state)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    backend_base_url: str = "https://backend-production-8b09.up.railway.app"  # OAuth redirect_uri
    frontend_base_url: str = "https://frontend-production-4fea.up.railway.app"  # post-callback
    # Daily caps assigned to a newly-registered (non-admin) account.
    default_daily_video_cap: int = 3
    default_daily_image_cap: int = 20

    # --- Cost guardrails (legacy/global defaults; per-user caps live on the account row) ---
    daily_video_cap: int = 10
    daily_image_cap: int = 40
    # Per-job cost rates (USD) — computed from actual duration/resolution/model at creation.
    cost_per_video_sec_720p: float = 0.10
    cost_per_video_sec_1080p: float = 0.15
    cost_per_image_usd: float = 0.03
    cost_per_image_pro_usd: float = 0.07

    @field_validator("db_url", mode="after")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        return _normalize_async_pg(v)

    @field_validator("test_database_url", mode="after")
    @classmethod
    def _normalize_test_db_url(cls, v: str | None) -> str | None:
        return _normalize_async_pg(v) if v else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
