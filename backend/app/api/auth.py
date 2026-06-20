"""Auth endpoints.

``public_router`` holds the un-gated routes (register/login/google) and is mounted on the
app WITHOUT the global ``current_auth`` dependency. ``router`` holds the gated routes
(/me, /rotate-token, /logout) and is mounted under the authenticated ``api_router``.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx, current_auth
from app.core.config import get_settings
from app.core.db import get_session
from app.core.logging import log
from app.schemas.api import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdatePreferencesRequest,
    UserRead,
)
from app.services import asset_service, auth_service, google_oauth, project_service

router = APIRouter(prefix="/auth", tags=["auth"])  # gated
public_router = APIRouter(prefix="/auth", tags=["auth"])  # un-gated


def _frontend(path: str) -> str:
    return get_settings().frontend_base_url.rstrip("/") + path


# --- public ---


@public_router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    try:
        user, token = await auth_service.register(session, body.email, body.password)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None
    log.info("auth.register user=%s", user.id)
    return AuthResponse(token=token, user=UserRead.from_user(user))


@public_router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await auth_service.authenticate(session, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = await auth_service.issue_token(session, user)
    log.info("auth.login user=%s", user.id)
    return AuthResponse(token=token, user=UserRead.from_user(user))


@public_router.get("/google/login")
async def google_login(request: Request):
    oauth = google_oauth.get_oauth()
    if oauth is None:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    redirect_uri = get_settings().backend_base_url.rstrip("/") + "/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@public_router.get("/google/callback")
async def google_callback(request: Request, session: AsyncSession = Depends(get_session)):
    oauth = google_oauth.get_oauth()
    if oauth is None:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:  # noqa: BLE001 - any OAuth failure bounces back to the frontend
        log.warning("auth.google callback failed")
        return RedirectResponse(_frontend("/auth/callback?error=oauth"))
    info = token.get("userinfo") or {}
    sub, email = info.get("sub"), info.get("email")
    if not sub or not email:
        return RedirectResponse(_frontend("/auth/callback?error=oauth"))
    user = await auth_service.upsert_google_user(session, sub, email)
    raw = await auth_service.issue_token(session, user)
    log.info("auth.google user=%s", user.id)
    return RedirectResponse(_frontend(f"/auth/callback?token={raw}"))


# --- gated ---


@router.get("/me", response_model=UserRead)
async def me(auth: AuthCtx = Depends(current_auth)):
    if auth.user is None:  # env admin master token
        return UserRead(
            id="admin",
            email="admin",
            is_admin=True,
            daily_video_cap=0,
            daily_image_cap=0,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            has_password=True,
            is_google=False,
        )
    return UserRead.from_user(auth.user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    body: UpdatePreferencesRequest,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Update account preferences (currently the advisory default format for new projects)."""
    if auth.user is None:
        raise HTTPException(status_code=400, detail="the admin account is managed via env, not here")
    auth.user.default_format = body.default_format.value if body.default_format else None
    session.add(auth.user)
    await session.commit()
    await session.refresh(auth.user)
    return UserRead.from_user(auth.user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
) -> None:
    if auth.user is None:
        raise HTTPException(status_code=400, detail="the admin account is managed via env, not here")
    try:
        await auth_service.change_password(
            session, auth.user, body.current_password, body.new_password
        )
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None
    log.info("auth.change_password user=%s", auth.user.id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    background_tasks: BackgroundTasks,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
) -> None:
    if auth.user is None:
        raise HTTPException(status_code=400, detail="the admin account is managed via env, not here")
    # Cascade the user's projects first (same child-first delete the project endpoint uses), then
    # the user row. Bucket cleanup runs after the response so the request never outlives the proxy.
    projects = await project_service.list_projects(session, owner_id=auth.user.id, is_admin=False)
    keys: list[str] = []
    for project in projects:
        keys.extend(await project_service.delete_project(session, project))
    await auth_service.delete_user(session, auth.user)
    log.info("auth.delete_user user=%s projects=%d", auth.user.id, len(projects))
    if keys:
        background_tasks.add_task(asset_service.delete_objects, keys)


@router.post("/rotate-token")
async def rotate_token(
    auth: AuthCtx = Depends(current_auth), session: AsyncSession = Depends(get_session)
) -> dict:
    if auth.user is None:
        raise HTTPException(status_code=400, detail="admin token is managed via env, not here")
    token = await auth_service.rotate_token(session, auth.user)
    return {"token": token}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    # Stateless: the client drops its stored token. Use /rotate-token to truly revoke.
    return None
