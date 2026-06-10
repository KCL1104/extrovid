"""Read endpoints for stored planning artifacts + per-shot direction edits + keyframes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.schemas.api import ConceptSetRead, LookFrameRead, SceneRead, ShotRead, ShotUpdate
from app.services import asset_service, imagegen_service, planning_service

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


@router.post("/shots/{shot_id}/keyframe", response_model=LookFrameRead)
async def generate_keyframe(
    project_id: str,
    shot_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Generate the shot's opening keyframe image (re-running replaces the pointer).

    The keyframe becomes the shot's i2v/r2v first-frame seed; refine it via the
    standard /look-frames/{id}/refine loop before spending video budget.
    """
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="shot not found")
    frame = await imagegen_service.generate_shot_keyframe(session, project_id, shot, auth=auth)
    return (await asset_service.frames_to_read(session, [frame]))[0]


@router.post("/storyboard/keyframes", response_model=list[LookFrameRead])
async def generate_all_keyframes(
    project_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Generate keyframes for every shot that doesn't have one yet (sequential)."""
    shots = await planning_service.list_shots(session, project_id)
    todo = [s for s in shots if not s.keyframe_frame_id]
    frames = []
    for shot in todo:
        frames.append(
            await imagegen_service.generate_shot_keyframe(session, project_id, shot, auth=auth)
        )
    return await asset_service.frames_to_read(session, frames)
