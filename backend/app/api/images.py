"""Previsual image layer: generate concept images and promote look frames."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.enums import PromotedAs
from app.schemas.api import LookFrameRead, PromoteRequest, RefineFrameRequest
from app.services import asset_service, imagegen_service, promote_service

router = APIRouter(
    prefix="/projects/{project_id}", tags=["images"], dependencies=[Depends(get_owned_project)]
)


@router.post("/concept-sets/{concept_set_id}/generate-images", response_model=list[LookFrameRead])
async def generate_concept_images(
    project_id: str,
    concept_set_id: str,
    limit: int | None = None,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    try:
        frames = await imagegen_service.generate_images_for_concept_set(
            session, project_id, concept_set_id, auth=auth, limit=limit
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
    if body.target == PromotedAs.NONE:
        raise HTTPException(status_code=422, detail="target must not be 'none'")
    try:
        return await promote_service.promote_look_frame(
            session, project_id, frame_id, body.target, body.name
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="look frame not found") from None


@router.post("/look-frames/{frame_id}/refine", response_model=LookFrameRead)
async def refine_frame(
    project_id: str,
    frame_id: str,
    body: RefineFrameRequest,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Iteratively refine a look frame with Qwen-Image-Edit (new frame, kept lineage)."""
    try:
        frame = await imagegen_service.refine_look_frame(
            session, project_id, frame_id, body.instruction, auth=auth
        )
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return (await asset_service.frames_to_read(session, [frame]))[0]
