"""Read endpoints for stored planning artifacts + per-shot direction edits + keyframes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.concept import LookFrame
from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.schemas.api import ConceptSetRead, LookFrameRead, SceneRead, ShotRead, ShotUpdate
from app.services import (
    asset_service,
    audio_service,
    imagegen_service,
    planning_service,
    review_service,
)

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
    shots = await planning_service.list_shots(session, project_id)
    # join each shot's keyframe gate verdict so the board can flag "revise" before render
    kf_ids = [s.keyframe_frame_id for s in shots if s.keyframe_frame_id]
    keyframes: dict[str, LookFrame] = {}
    if kf_ids:
        rows = (await session.execute(select(LookFrame).where(LookFrame.id.in_(kf_ids)))).scalars()
        keyframes = {f.id: f for f in rows}
    out: list[ShotRead] = []
    for s in shots:
        read = ShotRead.model_validate(s)
        kf = keyframes.get(s.keyframe_frame_id) if s.keyframe_frame_id else None
        if kf is not None:
            read.keyframe_verdict = (kf.review or {}).get("verdict")
            read.keyframe_score = kf.score
            read.keyframe_url = await asset_service.asset_url(session, kf.image_asset_id)
        out.append(read)
    return out


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


@router.post("/shots/{shot_id}/keyframe/review", response_model=LookFrameRead)
async def review_shot_keyframe(
    project_id: str,
    shot_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Re-run the keyframe gate (identity/composition/view) for this shot's keyframe."""
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="shot not found")
    if not shot.keyframe_frame_id:
        raise HTTPException(status_code=404, detail="shot has no keyframe to review")
    frame = await session.get(LookFrame, shot.keyframe_frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="keyframe not found")
    character = (
        await session.get(CharacterProfile, shot.character_id) if shot.character_id else None
    )
    await review_service.review_keyframe(session, frame, shot, character)
    await session.commit()
    return (await asset_service.frames_to_read(session, [frame]))[0]


@router.post("/shots/{shot_id}/voiceover", response_model=ShotRead)
async def generate_shot_voiceover(
    project_id: str,
    shot_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Synthesize the shot's spoken line into a stored voiceover asset (TTS, audio-capped)."""
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="shot not found")
    try:
        await audio_service.synthesize_shot_voiceover(session, project_id, shot, auth=auth)
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return ShotRead.model_validate(shot)


@router.post("/storyboard/voiceovers", response_model=list[ShotRead])
async def generate_all_voiceovers(
    project_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Synthesize a voiceover for every shot that has a line but no audio yet (sequential)."""
    shots = await planning_service.list_shots(session, project_id)
    out: list[ShotRead] = []
    for shot in shots:
        if (shot.dialogue or "").strip() and not shot.vo_asset_id:
            await audio_service.synthesize_shot_voiceover(session, project_id, shot, auth=auth)
            out.append(ShotRead.model_validate(shot))
    return out


@router.post("/storyboard/keyframes", response_model=list[LookFrameRead])
async def generate_all_keyframes(
    project_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Generate missing keyframes (sequential): an opening keyframe for every shot, plus a
    closing keyframe for every shot that has a successor (its continuity seed for chaining)."""
    shots = await planning_service.list_shots(session, project_id)
    max_order = max((s.order for s in shots), default=-1)
    frames = []
    for shot in shots:
        if not shot.keyframe_frame_id:
            frames.append(
                await imagegen_service.generate_shot_keyframe(session, project_id, shot, auth=auth)
            )
        # only shots something continues FROM need a closing keyframe (skip the final shot)
        if shot.order < max_order and shot.last_frame_desc and not shot.last_keyframe_frame_id:
            frames.append(
                await imagegen_service.generate_shot_keyframe(
                    session, project_id, shot, auth=auth, kind="last"
                )
            )
    return await asset_service.frames_to_read(session, frames)
