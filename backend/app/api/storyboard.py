"""Read endpoints for stored planning artifacts + per-shot direction edits."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.schemas.api import ConceptSetRead, SceneRead, ShotRead, ShotUpdate
from app.services import asset_service, planning_service

router = APIRouter(
    prefix="/projects/{project_id}", tags=["reads"], dependencies=[Depends(get_owned_project)]
)


@router.get("/script", response_model=list[SceneRead])
async def get_script(project_id: str, session: AsyncSession = Depends(get_session)):
    return await planning_service.list_scenes(session, project_id)


@router.get("/concept-sets", response_model=list[ConceptSetRead])
async def get_concept_sets(project_id: str, session: AsyncSession = Depends(get_session)):
    pairs = await planning_service.list_concept_sets(session, project_id)
    return [
        ConceptSetRead(
            id=cs.id,
            scene_order=cs.scene_order,
            brief=cs.brief,
            type=cs.type,
            status=cs.status,
            visual_brief=cs.visual_brief,
            look_frames=await asset_service.frames_to_read(session, frames),
        )
        for cs, frames in pairs
    ]


@router.get("/storyboard", response_model=list[ShotRead])
async def get_storyboard(project_id: str, session: AsyncSession = Depends(get_session)):
    return await planning_service.list_shots(session, project_id)


@router.patch("/shots/{shot_id}", response_model=ShotRead)
async def update_shot(
    project_id: str,
    shot_id: str,
    body: ShotUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Per-shot detailed direction: edit specs, transition, director's notes, cast lock."""
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="shot not found")
    if "character_id" in body.model_fields_set and body.character_id is not None:
        character = await session.get(CharacterProfile, body.character_id)
        if character is None or character.project_id != project_id:
            raise HTTPException(status_code=404, detail="character not found")
    shot = await planning_service.update_shot(session, shot, body)
    await session.commit()
    return shot
