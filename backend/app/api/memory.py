"""Reusable production memory reads: characters + style packs (promoted look frames)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _get_or_404
from app.core.db import get_session
from app.schemas.api import CharacterRead, StylePackRead
from app.services import memory_service

router = APIRouter(prefix="/projects/{project_id}", tags=["memory"])


@router.get("/characters", response_model=list[CharacterRead])
async def list_characters(project_id: str, session: AsyncSession = Depends(get_session)):
    await _get_or_404(session, project_id)
    return await memory_service.list_characters(session, project_id)


@router.get("/style-packs", response_model=list[StylePackRead])
async def list_style_packs(project_id: str, session: AsyncSession = Depends(get_session)):
    await _get_or_404(session, project_id)
    return await memory_service.list_style_packs(session, project_id)
