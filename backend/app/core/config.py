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
    qwen_model: str = "qwen3.7-plus"  # balanced default (1M ctx, ~6x cheaper than max) for all
    # non-script agents per docs.qwencloud.com model-selection
    # Script generation is the most creative/long-form step — route it to the flagship while
    # the other agents (brief/cast/storyboard/review/director) keep qwen_model. Qwen3.7-Max is
    # Alibaba's flagship ("The Agent Frontier"): 1M ctx, stronger creative writing + instruction
    # following. enable_thinking is still forced off in the factory (structured tool output).
    qwen_script_model: str = "qwen3.7-max"
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    llm_retries: int = 2

    # --- Image generation (Qwen-Image, DashScope-native sync endpoint) ---
    use_mock_image: bool = True  # mock generator + in-memory storage (offline/free)
    # Image generation (concept frames / keyframes / portraits). wan2.7-image-pro = Wan2.7's Pro
    # image model (up to 4K) — same DashScope multimodal-generation endpoint + request/response
    # shape as qwen-image, so it's a drop-in model-id swap. Field name kept for blast radius.
    qwen_image_model: str = "wan2.7-image-pro"
    # Refine/edit also uses wan2.7-image-pro — the Wan2.7 image family is unified (gen + edit
    # share one model id on the same multimodal-generation endpoint; the edit call just adds the
    # source image to the message content), so this is a drop-in swap too.
    qwen_image_edit_model: str = "wan2.7-image-pro"
    dashscope_image_url: str = (
        "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )

    # --- Text-to-speech (DashScope qwen3-tts; voiceover per shot) ---
    use_mock_tts: bool = True  # mock synthesizer (offline/free); deterministic MOCK_WAV
    # NOTE: verify endpoint + response envelope + intl-region availability against a live
    # key before flipping use_mock_tts off — qwen3-tts is a SEPARATE model family from
    # Qwen-Image and does NOT share the image response shape.
    qwen_tts_model: str = "qwen3-tts-flash"
    qwen_tts_instruct_model: str = "qwen3-tts-instruct-flash"  # when a voice instruction is set
    dashscope_tts_url: str = (
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
    # Video provider seam (see app/providers/video_factory.py). Both providers ride the SAME
    # DashScope video-synthesis async endpoint + DASHSCOPE_API_KEY below — the flag only selects
    # which model id each routing mode maps to. "happyhorse" = HappyHorse-1.0 (Alibaba; #1 on the
    # Artificial Analysis Video Arena — T2V ~1374 / I2V ~1410 Elo, ~+140 over Wan — native audio +
    # 7-language lip-sync). HappyHorse is the DEFAULT and has full t2v/i2v/r2v/video-edit parity on
    # DashScope. Set VIDEO_PROVIDER=wan to route every mode back to Wan instead.
    video_provider: str = "happyhorse"  # "happyhorse" | "wan"
    happyhorse_t2v_model: str = "happyhorse-1.0-t2v"
    happyhorse_i2v_model: str = "happyhorse-1.0-i2v"
    happyhorse_r2v_model: str = "happyhorse-1.0-r2v"
    happyhorse_videoedit_model: str = "happyhorse-1.0-video-edit"
    dashscope_video_url: str = (
        "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
    )
    dashscope_task_url: str = "https://dashscope-intl.aliyuncs.com/api/v1/tasks"
    video_resolution: str = "720P"
    video_reconcile_interval_sec: int = 10
    video_job_timeout_sec: int = 600  # stuck RUNNING jobs older than this -> FAILED
    sse_keepalive_sec: int = 15  # SSE idle ping so the Railway proxy doesn't cut the socket

    # --- HTTP resilience (provider 429/5xx retry with backoff) ---
    http_max_retries: int = 3
    http_retry_base_sec: float = 1.0

    # --- Proactive provider rate limits (requests/minute; 0 = unlimited) ---
    video_rpm: int = 2
    image_rpm: int = 10

    # --- Object storage (Railway / Tigris S3-compatible) ---
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    # boto3 signature version for the S3 client. Leave unset for AWS/Tigris (SigV4 default);
    # set to "s3" for Alibaba OSS, which rejects SigV4-with-chunked-encoding on uploads.
    s3_signature_version: str | None = None
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
    backend_base_url: str = "https://www.extrovid.xyz"  # OAuth redirect_uri (override per env)
    frontend_base_url: str = "https://www.extrovid.xyz"  # post-callback (override per env)
    # Daily caps assigned to a newly-registered (non-admin) account.
    default_daily_video_cap: int = 3
    default_daily_image_cap: int = 20
    default_daily_audio_cap: int = 30  # TTS voiceover lines/day (cheap, but billable)

    # --- Cost guardrails (legacy/global defaults; per-user caps live on the account row) ---
    daily_video_cap: int = 10
    daily_image_cap: int = 40
    daily_audio_cap: int = 60
    # Per-job cost rates (USD) — computed from actual duration/resolution/model at creation.
    # Video per-second rates for the default provider (HappyHorse-1.0): 720p $0.14/s, 1080p
    # $0.28/s. r2v/video-edit run slightly higher but we keep one base rate per resolution.
    # Drives est_spend_usd + per-user caps; set VIDEO_PROVIDER=wan → adjust to Wan's rates.
    cost_per_video_sec_720p: float = 0.14
    cost_per_video_sec_1080p: float = 0.28
    cost_per_image_usd: float = 0.03
    cost_per_image_pro_usd: float = 0.07
    cost_per_tts_usd: float = 0.02  # per synthesized voiceover line

    @field_validator("video_provider", mode="after")
    @classmethod
    def _validate_video_provider(cls, v: str) -> str:
        v = (v or "wan").lower()
        if v not in ("wan", "happyhorse"):
            raise ValueError("video_provider must be 'wan' or 'happyhorse'")
        return v

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
