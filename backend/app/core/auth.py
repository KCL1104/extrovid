"""Per-user token auth + the cost-cap exception.

``current_auth`` resolves the Bearer credential to an :class:`AuthCtx`: either the env
``API_TOKEN`` (admin — unlimited caps, sees every project) or a per-user opaque token
(caps come from the user row). It gates every ``/api`` route *except* the public
auth/gallery endpoints, which are mounted on a separate router with no auth dependency.
``CapExceeded`` is raised by the usage service and mapped to HTTP 429.
"""

import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.logging import log
from app.models.user import User
from app.services import auth_service


@dataclass
class AuthCtx:
    """Resolved identity for a request. ``video_cap``/``image_cap`` of 0 mean unlimited."""

    user: User | None  # None on the env-admin path (no user row)
    is_admin: bool
    user_id: str | None  # user.id, or None for env-admin
    video_cap: int
    image_cap: int


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer ") :]


async def current_auth(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> AuthCtx:
    settings = get_settings()
    raw = _bearer(authorization)
    if raw is None:
        log.warning("auth.denied reason=missing")
        raise HTTPException(status_code=401, detail="invalid or missing access token")
    # 1) Admin master token (env) — special-cased, no user row required.
    if settings.api_token and secrets.compare_digest(raw, settings.api_token):
        return AuthCtx(user=None, is_admin=True, user_id=None, video_cap=0, image_cap=0)
    # 2) Per-user opaque token (indexed sha256 lookup).
    user = await auth_service.get_by_token(session, raw)
    if user is not None:
        return AuthCtx(
            user=user,
            is_admin=user.is_admin,
            user_id=user.id,
            video_cap=0 if user.is_admin else user.daily_video_cap,
            image_cap=0 if user.is_admin else user.daily_image_cap,
        )
    log.warning("auth.denied reason=invalid")
    raise HTTPException(status_code=401, detail="invalid or missing access token")


class CapExceeded(Exception):
    """Raised when a daily paid-operation cap would be exceeded."""

    def __init__(self, kind: str, remaining: int):
        self.kind = kind
        self.remaining = remaining
        super().__init__(f"daily {kind} cap reached ({remaining} remaining today)")
