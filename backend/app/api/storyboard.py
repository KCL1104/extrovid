"""Read endpoints for stored planning artifacts."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _get_or_404
from app.core.db import get_session
from app.schemas.api import ConceptSetRead, SceneRead, ShotRead
from app.services import asset_service, planning_service

router = APIRouter(prefix="/projects/{project_id}", tags=["reads"])


@router.get("/script", response_model=list[SceneRead])
async def get_script(project_id: str, session: AsyncSession = Depends(get_session)):
    await _get_or_404(session, project_id)
    return await planning_service.list_scenes(session, project_id)


@router.get("/concept-sets", response_model=list[ConceptSetRead])
async def get_concept_sets(project_id: str, session: AsyncSession = Depends(get_session)):
    await _get_or_404(session, project_id)
    pairs = await planning_service.list_concept_sets(session, project_id)
    return [
        ConceptSetRead(
            id=cs.id,
            scene_order=cs.scene_order,
            brief=cs.brief,
            type=cs.type,
            status=cs.status,
            look_frames=await asset_service.frames_to_read(session, frames),
        )
        for cs, frames in pairs
    ]


@router.get("/storyboard", response_model=list[ShotRead])
async def get_storyboard(project_id: str, session: AsyncSession = Depends(get_session)):
    await _get_or_404(session, project_id)
    return await planning_service.list_shots(session, project_id)
