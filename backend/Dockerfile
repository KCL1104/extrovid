# Backend image for Railway. uv-based, runs migrations then serves FastAPI.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# install deps first (cached layer), then the project
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Railway provides $PORT. Run migrations on boot, then serve.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
