"""Usage + cost visibility (today's paid-op counts, caps, estimated spend)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.services import usage_service

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def get_usage(
    auth: AuthCtx = Depends(current_auth), session: AsyncSession = Depends(get_session)
) -> dict:
    return await usage_service.usage(session, auth)
