"""Shot video generation lifecycle over Wan (async) — activates ShotVersion + GenerationJob.

Mock mode completes on submit (instant fake MP4). Real mode submits an async Wan task and
relies on poll_and_ingest_job (called by the reconciler loop or the refresh endpoint) to
download the finished video into object storage when the task succeeds.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.core.pricing import video_cost_usd
from app.models.concept import LookFrame
from app.models.enums import JobStatus, PreferredModel, PromotedAs, ShotVersionStatus
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile
from app.models.project import Project
from app.models.shot import Shot
from app.providers.video_factory import (
    MOCK_MP4,
    download_bytes,
    poll_video,
    submit_video,
    submit_videoedit,
)
from app.services.asset_service import asset_url, store_bytes
from app.services.usage_service import assert_within_cap


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _ratio_for(aspect: str) -> str:
    return aspect if aspect in {"16:9", "9:16", "1:1"} else "9:16"


def _shot_prompt(shot: Shot) -> str:
    cam = shot.camera_spec or {}
    perf = shot.performance_spec or {}
    parts = [shot.purpose, f"{perf.get('subject', '')} {perf.get('action', '')}".strip()]
    if perf.get("emotion"):
        parts.append(f"mood: {perf['emotion']}")
    cam_desc = " ".join(filter(None, [cam.get("shot_size"), cam.get("angle"), cam.get("movement")]))
    if cam_desc:
        parts.append(f"camera: {cam_desc}")
    parts.append(f"beat: {shot.beat}")
    return ". ".join(p for p in parts if p)


async def _auto_first_frame_asset_id(session: AsyncSession, project_id: str) -> str | None:
    row = (
        (
            await session.execute(
                select(LookFrame).where(
                    LookFrame.project_id == project_id,
                    LookFrame.promoted_as == PromotedAs.FIRST_FRAME.value,
                    LookFrame.image_asset_id.is_not(None),
                )
            )
        )
        .scalars()
        .first()
    )
    return row.image_asset_id if row else None


async def _resolve_reference_urls(
    session: AsyncSession,
    project_id: str,
    reference_asset_ids: list[str] | None,
    character_id: str | None,
) -> list[str]:
    asset_ids: list[str] = list(reference_asset_ids or [])
    if character_id:
        cp = await session.get(CharacterProfile, character_id)
        if cp and cp.project_id == project_id:
            for fid in cp.reference_look_frame_ids:
                lf = await session.get(LookFrame, fid)
                if lf and lf.image_asset_id:
                    asset_ids.append(lf.image_asset_id)
    urls: list[str] = []
    for aid in dict.fromkeys(asset_ids):  # dedupe, keep order
        u = await asset_url(session, aid)
        if u:
            urls.append(u)
    return urls[:5]


async def submit_shot(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    first_frame_asset_id: str | None = None,
    reference_asset_ids: list[str] | None = None,
    character_id: str | None = None,
) -> tuple[ShotVersion, GenerationJob]:
    settings = get_settings()
    await assert_within_cap(session, "video", 1)
    project = await session.get(Project, project_id)
    ratio = _ratio_for(project.aspect_ratio if project else "")
    duration = max(2, min(15, round(shot.duration_sec)))
    prompt = _shot_prompt(shot)

    reference_urls = await _resolve_reference_urls(
        session, project_id, reference_asset_ids, character_id
    )
    if reference_urls:
        prompt = "The main subject matches the reference image. " + prompt

    if first_frame_asset_id is None and shot.preferred_model == PreferredModel.I2V.value:
        first_frame_asset_id = await _auto_first_frame_asset_id(session, project_id)
    first_frame_url = (
        await asset_url(session, first_frame_asset_id) if first_frame_asset_id else None
    )

    version = ShotVersion(shot_id=shot.id, prompt=prompt, status=ShotVersionStatus.DRAFT.value)
    session.add(version)
    await session.flush()
    job = GenerationJob(
        shot_version_id=version.id, provider="dashscope", status=JobStatus.QUEUED.value
    )
    session.add(job)
    await session.flush()

    sub = await submit_video(
        prompt,
        ratio=ratio,
        duration=duration,
        first_frame_url=first_frame_url,
        reference_urls=reference_urls or None,
    )
    version.model = sub.model
    job.task_id = sub.task_id
    job.model = sub.model
    job.started_at = _now()
    job.cost_usd = (
        0.0 if settings.use_mock_video else video_cost_usd(duration, settings.video_resolution)
    )
    log.info(
        "shot.generate project=%s shot=%s model=%s dur=%ss cost=$%.3f refs=%d",
        project_id,
        shot.id,
        sub.model,
        duration,
        job.cost_usd,
        len(reference_urls),
    )

    if settings.use_mock_video:
        asset = await store_bytes(
            session,
            project_id,
            MOCK_MP4,
            "video/mp4",
            prompt=prompt,
            source_model=sub.model,
            use_mock=True,
        )
        version.output_asset_id = asset.id
        job.status = JobStatus.SUCCEEDED.value
        job.completed_at = _now()
    else:
        job.status = JobStatus.RUNNING.value

    session.add_all([version, job])
    await session.commit()
    return version, job


async def submit_shot_edit(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    source_version_id: str,
    instruction: str,
) -> tuple[ShotVersion, GenerationJob]:
    settings = get_settings()
    await assert_within_cap(session, "video", 1)
    source = await session.get(ShotVersion, source_version_id)
    if source is None or source.shot_id != shot.id or not source.output_asset_id:
        raise LookupError("source version has no video to edit")
    source_url = await asset_url(session, source.output_asset_id) or ""

    version = ShotVersion(
        shot_id=shot.id,
        parent_version_id=source_version_id,
        prompt=instruction,
        status=ShotVersionStatus.DRAFT.value,
    )
    session.add(version)
    await session.flush()
    job = GenerationJob(
        shot_version_id=version.id, provider="dashscope", status=JobStatus.QUEUED.value
    )
    session.add(job)
    await session.flush()

    sub = await submit_videoedit(source_url, instruction)
    version.model = sub.model
    job.task_id = sub.task_id
    job.model = sub.model
    job.started_at = _now()
    job.cost_usd = (
        0.0
        if settings.use_mock_video
        else video_cost_usd(float(shot.duration_sec), settings.video_resolution)
    )

    if settings.use_mock_video:
        asset = await store_bytes(
            session,
            project_id,
            MOCK_MP4,
            "video/mp4",
            prompt=instruction,
            source_model=sub.model,
            use_mock=True,
        )
        version.output_asset_id = asset.id
        job.status = JobStatus.SUCCEEDED.value
        job.completed_at = _now()
    else:
        job.status = JobStatus.RUNNING.value

    session.add_all([version, job])
    await session.commit()
    return version, job


async def poll_and_ingest_job(session: AsyncSession, job: GenerationJob) -> GenerationJob:
    if job.status != JobStatus.RUNNING.value:
        return job

    res = await poll_video(job.task_id)
    if res.status == "SUCCEEDED" and res.video_url and not res.video_url.startswith("mock://"):
        version = await session.get(ShotVersion, job.shot_version_id)
        shot = await session.get(Shot, version.shot_id) if version else None
        project_id = shot.project_id if shot else ""
        data = await download_bytes(res.video_url)
        asset = await store_bytes(
            session,
            project_id,
            data,
            "video/mp4",
            prompt=version.prompt if version else "",
            source_model=job.model or "",
            use_mock=False,
        )
        if version:
            version.output_asset_id = asset.id
            session.add(version)
        job.status = JobStatus.SUCCEEDED.value
        job.completed_at = _now()
        log.info("job.succeeded job=%s model=%s", job.id, job.model)
    elif res.status == "FAILED":
        job.status = JobStatus.FAILED.value
        job.failure_reason = res.failure
        job.completed_at = _now()
        log.warning("job.failed job=%s reason=%s", job.id, job.failure_reason)
    elif (
        job.started_at
        and (_now() - job.started_at).total_seconds() > get_settings().video_job_timeout_sec
    ):
        # still PENDING/RUNNING but stuck too long -> stop the spinner
        job.status = JobStatus.FAILED.value
        job.failure_reason = "timed out"
        job.completed_at = _now()
        log.warning("job.timeout job=%s", job.id)
    # else PENDING/RUNNING -> leave as-is for the next poll

    session.add(job)
    await session.commit()
    return job


async def reconcile_running(session: AsyncSession) -> int:
    jobs = (
        (
            await session.execute(
                select(GenerationJob).where(GenerationJob.status == JobStatus.RUNNING.value)
            )
        )
        .scalars()
        .all()
    )
    for job in jobs:
        try:
            await poll_and_ingest_job(session, job)
        except Exception:  # noqa: BLE001 - reconciler must not die on one bad job
            await session.rollback()
    return len(jobs)
