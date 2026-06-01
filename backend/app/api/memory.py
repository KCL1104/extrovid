"""Reusable production memory reads: characters + style packs (promoted look frames)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.schemas.api import CharacterRead, StylePackRead
from app.services import memory_service

router = APIRouter(
    prefix="/projects/{project_id}", tags=["memory"], dependencies=[Depends(get_owned_project)]
)


@router.get("/characters", response_model=list[CharacterRead])
async def list_characters(project_id: str, session: AsyncSession = Depends(get_session)):
    return await memory_service.list_characters(session, project_id)


@router.get("/style-packs", response_model=list[StylePackRead])
async def list_style_packs(project_id: str, session: AsyncSession = Depends(get_session)):
    return await memory_service.list_style_packs(session, project_id)
