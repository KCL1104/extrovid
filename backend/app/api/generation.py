"""Shot video generation endpoints (Wan t2v/i2v via the async GenerationJob lifecycle)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _get_or_404
from app.core.db import get_session
from app.models.generation import GenerationJob, ShotVersion
from app.models.shot import Shot
from app.schemas.api import EditShotRequest, GenerateShotRequest, ShotVersionRead
from app.services import generate_service
from app.services.asset_service import asset_url

router = APIRouter(prefix="/projects/{project_id}", tags=["generation"])


async def _shot_or_404(session: AsyncSession, project_id: str, shot_id: str) -> Shot:
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="shot not found")
    return shot


async def _version_read(
    session: AsyncSession, version: ShotVersion, job: GenerationJob | None
) -> ShotVersionRead:
    return ShotVersionRead(
        id=version.id,
        shot_id=version.shot_id,
        model=version.model,
        status=version.status,
        selected=version.selected,
        output_asset_id=version.output_asset_id,
        video_url=await asset_url(session, version.output_asset_id),
        job_id=job.id if job else None,
        job_status=job.status if job else None,
        failure_reason=job.failure_reason if job else None,
    )


@router.post("/shots/{shot_id}/generate", response_model=ShotVersionRead)
async def generate_shot(
    project_id: str,
    shot_id: str,
    body: GenerateShotRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    await _get_or_404(session, project_id)
    shot = await _shot_or_404(session, project_id, shot_id)
    version, job = await generate_service.submit_shot(
        session,
        project_id,
        shot,
        first_frame_asset_id=body.first_frame_asset_id if body else None,
        reference_asset_ids=body.reference_asset_ids if body else None,
        character_id=body.character_id if body else None,
    )
    return await _version_read(session, version, job)


@router.get("/shots/{shot_id}/versions", response_model=list[ShotVersionRead])
async def list_shot_versions(
    project_id: str, shot_id: str, session: AsyncSession = Depends(get_session)
):
    await _get_or_404(session, project_id)
    await _shot_or_404(session, project_id, shot_id)
    versions = (
        (await session.execute(select(ShotVersion).where(ShotVersion.shot_id == shot_id)))
        .scalars()
        .all()
    )
    out = []
    for v in versions:
        job = (
            (
                await session.execute(
                    select(GenerationJob).where(GenerationJob.shot_version_id == v.id)
                )
            )
            .scalars()
            .first()
        )
        out.append(await _version_read(session, v, job))
    return out


@router.post("/shots/{shot_id}/versions/{version_id}/edit", response_model=ShotVersionRead)
async def edit_version(
    project_id: str,
    shot_id: str,
    version_id: str,
    body: EditShotRequest,
    session: AsyncSession = Depends(get_session),
):
    await _get_or_404(session, project_id)
    shot = await _shot_or_404(session, project_id, shot_id)
    try:
        version, job = await generate_service.submit_shot_edit(
            session, project_id, shot, version_id, body.instruction
        )
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return await _version_read(session, version, job)


@router.post("/shots/{shot_id}/versions/{version_id}/select", response_model=ShotVersionRead)
async def select_version(
    project_id: str, shot_id: str, version_id: str, session: AsyncSession = Depends(get_session)
):
    await _get_or_404(session, project_id)
    await _shot_or_404(session, project_id, shot_id)
    siblings = (
        (await session.execute(select(ShotVersion).where(ShotVersion.shot_id == shot_id)))
        .scalars()
        .all()
    )
    target = next((v for v in siblings if v.id == version_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="version not found")
    for v in siblings:
        v.selected = v.id == version_id
        session.add(v)
    await session.commit()
    job = (
        (
            await session.execute(
                select(GenerationJob).where(GenerationJob.shot_version_id == target.id)
            )
        )
        .scalars()
        .first()
    )
    return await _version_read(session, target, job)


@router.post("/jobs/{job_id}/refresh", response_model=ShotVersionRead)
async def refresh_job(project_id: str, job_id: str, session: AsyncSession = Depends(get_session)):
    await _get_or_404(session, project_id)
    job = await session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    version = await session.get(ShotVersion, job.shot_version_id)
    shot = await session.get(Shot, version.shot_id) if version else None
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="job not found")
    job = await generate_service.poll_and_ingest_job(session, job)
    version = await session.get(ShotVersion, job.shot_version_id)
    return await _version_read(session, version, job)
