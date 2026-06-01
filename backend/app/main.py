"""FastAPI application factory."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router, public_router
from app.core.auth import CapExceeded, current_auth
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging


async def _reconciler_loop() -> None:
    """Poll RUNNING Wan jobs and ingest finished videos (real mode only)."""
    from app.core.db import SessionLocal
    from app.services.generate_service import reconcile_running

    interval = get_settings().video_reconcile_interval_sec
    while True:
        await asyncio.sleep(interval)
        try:
            async with SessionLocal() as session:
                await reconcile_running(session)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - loop must survive transient errors
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_create_db:
        await init_db()
    task: asyncio.Task | None = None
    if not settings.use_mock_video:
        task = asyncio.create_task(_reconciler_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="extrovid — AI-native director/editor",
        version="0.1.0",
        summary="Milestone 1: Brief -> Script -> Visual Brief -> Concept Set -> Storyboard.",
        lifespan=lifespan,
    )
    settings = get_settings()
    # SessionMiddleware added first → CORS (added last) stays outermost. The session cookie
    # only carries transient OAuth state during the Google redirect; the API itself is
    # Bearer-token based, so CORS needs no credentials.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Bearer-token auth, no cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api", dependencies=[Depends(current_auth)])
    app.include_router(public_router, prefix="/api")  # register/login/google — no auth gate

    @app.exception_handler(CapExceeded)
    async def _cap_exceeded(_: Request, exc: CapExceeded) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
