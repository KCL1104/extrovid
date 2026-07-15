"""Shot video generation endpoints (Wan t2v/i2v/r2v via the async GenerationJob lifecycle).

Also exposes the project-wide jobs queue (status / cost / retry) and the per-take AI
review — the production-management surface of the app.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core import event_bus
from app.core.auth import AuthCtx, current_auth
from app.core.config import get_settings
from app.core.db import get_session
from app.models.generation import GenerationJob, ShotVersion
from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.schemas.api import (
    BatchGenerateRequest,
    EditShotRequest,
    GenerateShotRequest,
    JobRead,
    ShotVersionRead,
)
from app.services import (
    generate_service,
    planning_service,
    review_gate_service,
    review_service,
)
from app.services.asset_service import asset_url

router = APIRouter(
    prefix="/projects/{project_id}", tags=["generation"], dependencies=[Depends(get_owned_project)]
)


def _gate(blockers: list[str]) -> None:
    """Block generation for gated tiers until the plan is approved at the review gate."""
    if blockers:
        raise HTTPException(status_code=409, detail="; ".join(blockers))


@router.get("/events")
async def project_events(project_id: str, request: Request):
    """Live job-progress stream (SSE). Additive to the 5s poll, which stays the fallback.

    Holds NO DB session for the stream's life — it only forwards bus events (IDs); the
    client refetches via the normal authed endpoints. A keepalive ping every
    ``sse_keepalive_sec`` stops the Railway proxy idle-cutting the socket."""
    queue = event_bus.subscribe(project_id)
    keepalive = get_settings().sse_keepalive_sec

    async def gen():
        try:
            yield event_bus.sse({"type": "ready"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=keepalive)
                    yield event_bus.sse(ev)
                except TimeoutError:
                    yield ":\n\n"  # comment-only keepalive frame
        finally:
            event_bus.unsubscribe(project_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        parent_version_id=version.parent_version_id,
        model=version.model,
        prompt=version.prompt,
        status=version.status,
        selected=version.selected,
        output_asset_id=version.output_asset_id,
        video_url=await asset_url(session, version.output_asset_id),
        thumbnail_url=await asset_url(session, version.thumbnail_asset_id),
        duration_sec=version.duration_sec,
        score=version.score,
        review=version.review,
        routing_note=version.routing_note,
        job_id=job.id if job else None,
        job_status=job.status if job else None,
        failure_reason=job.failure_reason if job else None,
    )


@router.post("/shots/{shot_id}/generate", response_model=ShotVersionRead)
async def generate_shot(
    project_id: str,
    shot_id: str,
    body: GenerateShotRequest | None = None,
    project: Project = Depends(get_owned_project),
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    shot = await _shot_or_404(session, project_id, shot_id)
    _gate(review_gate_service.shot_generation_blockers(project, shot))
    _gate(await review_gate_service.budget_blockers(session, project))
    try:
        takes = await generate_service.submit_shot_batch(
            session,
            project_id,
            shot,
            auth=auth,
            num_takes=body.num_takes if body else 1,
            first_frame_asset_id=body.first_frame_asset_id if body else None,
            reference_asset_ids=body.reference_asset_ids if body else None,
            reference_roles=body.reference_roles if body else None,
            character_id=body.character_id if body else None,
            continue_from_previous=body.continue_from_previous if body else False,
        )
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    # the first take answers the request; siblings are visible via /versions
    version, job = takes[0]
    await session.refresh(version)  # auto-select may have flipped `selected`
    return await _version_read(session, version, job)


async def _batch_response(
    session: AsyncSession, takes: list[tuple[ShotVersion, GenerationJob]]
) -> list[ShotVersionRead]:
    return [await _version_read(session, v, j) for v, j in takes]


@router.post("/scenes/{scene_order}/generate-all", response_model=list[ShotVersionRead])
async def generate_scene(
    project_id: str,
    scene_order: int,
    body: BatchGenerateRequest | None = None,
    project: Project = Depends(get_owned_project),
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Render every shot of one scene. Keyframed shots submit in parallel; with
    continue_from_previous, chain links queue until their upstream take lands."""
    shots = [
        s
        for s in await planning_service.list_shots(session, project_id)
        if s.scene_order == scene_order
    ]
    if not shots:
        raise HTTPException(status_code=404, detail="no shots in that scene")
    scene = (
        (
            await session.execute(
                select(Scene).where(Scene.project_id == project_id, Scene.order == scene_order)
            )
        )
        .scalars()
        .first()
    )
    _gate(review_gate_service.scene_generation_blockers(project, scene))
    _gate(await review_gate_service.budget_blockers(session, project))
    takes = await generate_service.submit_scene_batch(
        session,
        project_id,
        shots,
        auth=auth,
        continue_from_previous=body.continue_from_previous if body else False,
    )
    return await _batch_response(session, takes)


@router.post("/generate-all", response_model=list[ShotVersionRead])
async def generate_project(
    project_id: str,
    body: BatchGenerateRequest | None = None,
    project: Project = Depends(get_owned_project),
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Render every shot of the project in one request."""
    shots = await planning_service.list_shots(session, project_id)
    if not shots:
        raise HTTPException(status_code=404, detail="no storyboard yet")
    _gate(review_gate_service.project_generation_blockers(project))
    _gate(await review_gate_service.budget_blockers(session, project))
    takes = await generate_service.submit_scene_batch(
        session,
        project_id,
        shots,
        auth=auth,
        continue_from_previous=body.continue_from_previous if body else False,
    )
    return await _batch_response(session, takes)


@router.get("/shots/{shot_id}/versions", response_model=list[ShotVersionRead])
async def list_shot_versions(
    project_id: str, shot_id: str, session: AsyncSession = Depends(get_session)
):
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
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    shot = await _shot_or_404(session, project_id, shot_id)
    try:
        version, job = await generate_service.submit_shot_edit(
            session,
            project_id,
            shot,
            version_id,
            body.instruction,
            auth=auth,
            touches_audio=body.touches_audio,
        )
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return await _version_read(session, version, job)


@router.post("/shots/{shot_id}/versions/{version_id}/select", response_model=ShotVersionRead)
async def select_version(
    project_id: str, shot_id: str, version_id: str, session: AsyncSession = Depends(get_session)
):
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


@router.post("/shots/{shot_id}/versions/{version_id}/review", response_model=ShotVersionRead)
async def review_version(
    project_id: str, shot_id: str, version_id: str, session: AsyncSession = Depends(get_session)
):
    """(Re-)run the AI dailies review for a finished take."""
    await _shot_or_404(session, project_id, shot_id)
    version = await session.get(ShotVersion, version_id)
    if version is None or version.shot_id != shot_id:
        raise HTTPException(status_code=404, detail="version not found")
    if not version.output_asset_id:
        raise HTTPException(status_code=400, detail="take has no video to review yet")
    version = await review_service.review_version(session, version)
    await session.commit()
    job = (
        (
            await session.execute(
                select(GenerationJob).where(GenerationJob.shot_version_id == version.id)
            )
        )
        .scalars()
        .first()
    )
    return await _version_read(session, version, job)


@router.post("/jobs/{job_id}/refresh", response_model=ShotVersionRead)
async def refresh_job(project_id: str, job_id: str, session: AsyncSession = Depends(get_session)):
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


@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(project_id: str, session: AsyncSession = Depends(get_session)):
    """Every generation job in the project, newest first — the production queue."""
    rows = (
        await session.execute(
            select(GenerationJob, ShotVersion, Shot)
            .join(ShotVersion, GenerationJob.shot_version_id == ShotVersion.id)
            .join(Shot, ShotVersion.shot_id == Shot.id)
            .where(Shot.project_id == project_id)
            .order_by(GenerationJob.started_at.desc())
        )
    ).all()
    return [
        JobRead(
            id=job.id,
            status=job.status,
            provider=job.provider,
            model=job.model,
            started_at=job.started_at,
            completed_at=job.completed_at,
            failure_reason=job.failure_reason,
            cost_usd=job.cost_usd,
            shot_id=shot.id,
            shot_order=shot.order,
            shot_purpose=shot.purpose,
            version_id=version.id,
            thumbnail_url=await asset_url(session, version.thumbnail_asset_id),
        )
        for job, version, shot in rows
    ]


@router.post("/jobs/{job_id}/retry", response_model=ShotVersionRead)
async def retry_job(
    project_id: str,
    job_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Re-run a failed job with the same direction (creates a fresh take + job)."""
    job = await session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        version, new_job = await generate_service.retry_job(session, project_id, job, auth=auth)
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return await _version_read(session, version, new_job)
