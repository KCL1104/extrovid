"""User account table — backs per-user auth, ownership, and daily caps.

Named ``app_user`` (not ``user``) to avoid the reserved word in Postgres. The opaque
per-user access token is never stored; only its SHA-256 (``token_hash``) is, so lookups
stay an indexed O(1) ``WHERE token_hash = :h``. Passwords use argon2 (``password_hash``),
null for Google-only accounts.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = "app_user"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str | None = None  # null for Google-only accounts
    google_sub: str | None = Field(default=None, index=True, unique=True)
    token_hash: str = Field(index=True, unique=True)  # sha256 of the opaque access token
    daily_video_cap: int = 3
    daily_image_cap: int = 20
    is_admin: bool = False
    created_at: datetime = Field(default_factory=_now)
