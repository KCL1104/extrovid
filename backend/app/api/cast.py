"""Cast pipeline: extract planned characters from the script + portrait sheets."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.pipeline import orchestrator
from app.schemas.api import CharacterRead
from app.schemas.pipeline import ScriptDraft
from app.services import memory_service, planning_service, portrait_service

router = APIRouter(
    prefix="/projects/{project_id}", tags=["cast"], dependencies=[Depends(get_owned_project)]
)


@router.post("/cast/generate", response_model=list[CharacterRead])
async def generate_cast(
    project_id: str, session: AsyncSession = Depends(get_session)
):
    """Run the CastAgent over the persisted script and upsert CharacterProfiles.

    Existing profiles keep their reference frames/portraits; planned features refresh.
    """
    scenes = await planning_service.list_scenes(session, project_id)
    if not scenes:
        raise HTTPException(status_code=422, detail="no script yet — run /script first")
    script = ScriptDraft(
        logline=scenes[0].summary,
        scenes=[
            {
                "order": s.order,
                "title": s.title,
                "summary": s.summary,
                "beats": s.beats,
                "est_duration_sec": s.est_duration_sec,
            }
            for s in scenes
        ],
    )
    cast = await orchestrator.run_cast(script)
    await memory_service.upsert_cast(session, project_id, cast)
    await session.commit()
    return await memory_service.list_characters(session, project_id)


@router.post("/characters/{character_id}/portraits", response_model=CharacterRead)
async def generate_portraits(
    project_id: str,
    character_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Generate the canonical front/side/back portrait sheet (3 image generations)."""
    try:
        await portrait_service.generate_portrait_sheet(
            session, project_id, character_id, auth=auth
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    chars = await memory_service.list_characters(session, project_id)
    return next(c for c in chars if c.id == character_id)
