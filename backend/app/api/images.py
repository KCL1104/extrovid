"""Previsual image layer: generate concept images and promote look frames."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _get_or_404
from app.core.db import get_session
from app.models.enums import PromotedAs
from app.schemas.api import LookFrameRead, PromoteRequest
from app.services import asset_service, imagegen_service, promote_service

router = APIRouter(prefix="/projects/{project_id}", tags=["images"])


@router.post("/concept-sets/{concept_set_id}/generate-images", response_model=list[LookFrameRead])
async def generate_concept_images(
    project_id: str,
    concept_set_id: str,
    limit: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    await _get_or_404(session, project_id)
    try:
        frames = await imagegen_service.generate_images_for_concept_set(
            session, project_id, concept_set_id, limit=limit
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="concept set not found") from None
    return await asset_service.frames_to_read(session, frames)


@router.post("/look-frames/{frame_id}/promote")
async def promote_frame(
    project_id: str,
    frame_id: str,
    body: PromoteRequest,
    session: AsyncSession = Depends(get_session),
):
    await _get_or_404(session, project_id)
    if body.target == PromotedAs.NONE:
        raise HTTPException(status_code=422, detail="target must not be 'none'")
    try:
        return await promote_service.promote_look_frame(
            session, project_id, frame_id, body.target, body.name
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="look frame not found") from None
