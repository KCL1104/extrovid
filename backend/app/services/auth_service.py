"""Account lifecycle: register, authenticate, token lookup/issue, Google upsert, rotation.

The opaque access token is the API credential. We persist only its sha256 (``token_hash``);
a fresh token is minted on register and re-issued on every successful login / Google sign-in
/ explicit rotate (since the prior raw value can't be recovered from the hash). For the same
device this is rare in practice — the frontend persists the token and only re-auths on a new
device or after logout. The planned move to session-based auth removes this caveat entirely.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, hash_token, new_opaque_token, verify_password
from app.models.user import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """Auth-domain failure, mapped to a 4xx by the API layer."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    res = await session.execute(select(User).where(User.email == _normalize_email(email)))
    return res.scalars().first()


async def get_by_token(session: AsyncSession, raw_token: str) -> User | None:
    res = await session.execute(select(User).where(User.token_hash == hash_token(raw_token)))
    return res.scalars().first()


async def issue_token(session: AsyncSession, user: User) -> str:
    """Mint a fresh opaque token, store its hash, return the raw value (shown once)."""
    raw = new_opaque_token()
    user.token_hash = hash_token(raw)
    session.add(user)
    await session.commit()
    return raw


# rotate_token is just an explicit, user-triggered re-issue.
rotate_token = issue_token


async def register(session: AsyncSession, email: str, password: str) -> tuple[User, str]:
    email = _normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise AuthError(422, "invalid email address")
    if len(password) < 8:
        raise AuthError(422, "password must be at least 8 characters")
    if await get_by_email(session, email):
        raise AuthError(409, "an account with this email already exists")
    settings = get_settings()
    raw = new_opaque_token()
    user = User(
        email=email,
        password_hash=hash_password(password),
        token_hash=hash_token(raw),
        daily_video_cap=settings.default_daily_video_cap,
        daily_image_cap=settings.default_daily_image_cap,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, raw


async def change_password(
    session: AsyncSession, user: User, current_password: str | None, new_password: str
) -> None:
    """Set a new password. Accounts that already have one must prove the current password;
    Google-only accounts (no password) set their first without one. Does NOT rotate the token —
    the current device stays signed in; "reset access" (rotate_token) is the explicit revoke."""
    if len(new_password) < 8:
        raise AuthError(422, "password must be at least 8 characters")
    if user.password_hash is not None:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise AuthError(403, "current password is incorrect")
    user.password_hash = hash_password(new_password)
    session.add(user)
    await session.commit()


async def delete_user(session: AsyncSession, user: User) -> None:
    """Delete the user row. The caller is responsible for cascading the user's projects first."""
    await session.delete(user)
    await session.commit()


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_by_email(session, email)
    if user is None or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def upsert_google_user(session: AsyncSession, google_sub: str, email: str) -> User:
    # Prefer an existing google-linked account, then an existing email account, else create.
    res = await session.execute(select(User).where(User.google_sub == google_sub))
    user = res.scalars().first()
    if user:
        return user
    user = await get_by_email(session, email)
    if user:
        user.google_sub = google_sub
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    settings = get_settings()
    raw = new_opaque_token()
    user = User(
        email=_normalize_email(email),
        google_sub=google_sub,
        token_hash=hash_token(raw),
        daily_video_cap=settings.default_daily_video_cap,
        daily_image_cap=settings.default_daily_image_cap,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
