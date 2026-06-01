"""Rough-cut assembly + export endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.models.timeline import TimelineSequence
from app.schemas.api import RoughCutRead
from app.services import rough_cut_service
from app.services.asset_service import asset_url

router = APIRouter(
    prefix="/projects/{project_id}", tags=["rough-cut"], dependencies=[Depends(get_owned_project)]
)


async def _read(session: AsyncSession, seq: TimelineSequence) -> RoughCutRead:
    return RoughCutRead(
        id=seq.id,
        status=seq.status,
        output_asset_id=seq.output_asset_id,
        video_url=await asset_url(session, seq.output_asset_id),
        shot_version_ids=seq.shot_version_ids,
    )


@router.post("/rough-cut", response_model=RoughCutRead)
async def assemble(project_id: str, session: AsyncSession = Depends(get_session)):
    try:
        seq = await rough_cut_service.assemble_rough_cut(session, project_id)
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return await _read(session, seq)


@router.get("/rough-cut", response_model=list[RoughCutRead])
async def list_rough_cuts(project_id: str, session: AsyncSession = Depends(get_session)):
    seqs = await rough_cut_service.list_rough_cuts(session, project_id)
    return [await _read(session, s) for s in seqs]
