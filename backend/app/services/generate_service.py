"""Shot video generation lifecycle over Wan (async) — the AI-native production engine.

Per take this service now:
- composes the final prompt from project memory (visual brief, style pack, character)
- routes the shot to a Wan model and records WHY (``routing_note``)
- supports shot-to-shot continuation (previous take's last frame -> next shot's i2v seed)
- on ingest: probes real duration, extracts a poster thumbnail, and runs the ReviewAgent
  so every finished take carries a score + director's notes + revision suggestions

Mock mode completes on submit (instant fake MP4). Real mode submits an async Wan task and
relies on poll_and_ingest_job (called by the reconciler loop or the refresh endpoint).
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx
from app.core.config import get_settings
from app.core.logging import log
from app.core.pricing import video_cost_usd
from app.models.asset import ImageAsset
from app.models.concept import LookFrame, VisualConceptSet
from app.models.enums import JobStatus, PreferredModel, PromotedAs, ShotVersionStatus
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile, StylePack
from app.models.project import Brief, Project
from app.models.shot import Shot
from app.providers.video_factory import (
    MOCK_MP4,
    download_bytes,
    poll_video,
    submit_video,
    submit_videoedit,
)
from app.services import media_service, review_service
from app.services.asset_service import asset_url, load_bytes, store_bytes
from app.services.prompt_service import compose_negative_prompt, compose_shot_prompt
from app.services.usage_service import assert_within_cap


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _ratio_for(aspect: str) -> str:
    return aspect if aspect in {"16:9", "9:16", "1:1"} else "9:16"


async def _scene_visual_brief(session: AsyncSession, shot: Shot) -> dict | None:
    if not shot.scene_id:
        return None
    cs = (
        (
            await session.execute(
                select(VisualConceptSet).where(VisualConceptSet.scene_id == shot.scene_id)
            )
        )
        .scalars()
        .first()
    )
    return cs.visual_brief if cs else None


async def _project_style_pack(session: AsyncSession, project_id: str) -> StylePack | None:
    return (
        (await session.execute(select(StylePack).where(StylePack.project_id == project_id)))
        .scalars()
        .first()
    )


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


async def _continuation_frame_asset_id(
    session: AsyncSession, project_id: str, shot: Shot
) -> tuple[str, str]:
    """Extract the previous take's last frame as a stored image asset (the i2v/r2v seed).

    Returns (asset_id, note). Raises LookupError when there is nothing to continue from.
    """
    found = await review_service.previous_shot_take(session, project_id, shot)
    if found is None:
        raise LookupError("no finished take on a previous shot to continue from")
    prev_shot, prev_version = found
    settings = get_settings()
    src_asset = await session.get(ImageAsset, prev_version.output_asset_id)
    frame: bytes | None = None
    if src_asset is not None:
        data = await load_bytes(src_asset)
        frame = await asyncio.to_thread(media_service.extract_last_frame, data)
    if frame is None:
        if not settings.use_mock_video:
            raise LookupError("could not extract a continuation frame from the previous take")
        # mock clips are not decodable — use a placeholder frame so the flow stays testable
        from app.providers.image_factory import _MOCK_PNG

        frame = _MOCK_PNG
    asset = await store_bytes(
        session,
        project_id,
        frame,
        "image/jpeg" if frame[:3] == b"\xff\xd8\xff" else "image/png",
        prompt=f"continuation frame — last frame of shot #{prev_shot.order}",
        source_model="ffmpeg:last-frame",
        use_mock=settings.use_mock_video,
    )
    return asset.id, f"continues from shot #{prev_shot.order}'s last frame"


async def _ingest_video_bytes(
    session: AsyncSession,
    project_id: str,
    version: ShotVersion,
    data: bytes,
    *,
    use_mock: bool,
    source_model: str,
) -> None:
    """Store the finished clip, probe it, and attach a poster thumbnail."""
    asset = await store_bytes(
        session,
        project_id,
        data,
        "video/mp4",
        prompt=version.prompt or "",
        source_model=source_model,
        use_mock=use_mock,
    )
    version.output_asset_id = asset.id
    info = await asyncio.to_thread(media_service.probe_video, data)
    if info and info.duration_sec:
        version.duration_sec = round(info.duration_sec, 2)
    poster = await asyncio.to_thread(media_service.extract_poster, data)
    if poster is not None:
        thumb = await store_bytes(
            session,
            project_id,
            poster,
            "image/jpeg",
            prompt=f"poster frame — {version.prompt or ''}"[:200],
            source_model="ffmpeg:poster",
            use_mock=use_mock,
        )
        version.thumbnail_asset_id = thumb.id
    session.add(version)


async def submit_shot(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    *,
    auth: AuthCtx,
    first_frame_asset_id: str | None = None,
    reference_asset_ids: list[str] | None = None,
    character_id: str | None = None,
    continue_from_previous: bool = False,
) -> tuple[ShotVersion, GenerationJob]:
    settings = get_settings()
    await assert_within_cap(session, "video", 1, auth=auth)
    project = await session.get(Project, project_id)
    ratio = _ratio_for(project.aspect_ratio if project else "")
    duration = max(2, min(15, round(shot.duration_sec)))

    if character_id is None:
        # cast lock: the shot's persisted character is the default; an explicit request wins
        character_id = shot.character_id

    gen_params = {
        "first_frame_asset_id": first_frame_asset_id,
        "reference_asset_ids": reference_asset_ids,
        "character_id": character_id,
        "continue_from_previous": continue_from_previous,
    }

    reference_urls = await _resolve_reference_urls(
        session, project_id, reference_asset_ids, character_id
    )

    # --- routing: decide the input mode and record why ---
    continuation_note: str | None = None
    if continue_from_previous and first_frame_asset_id is None:
        # the seed composes with references too: r2v accepts a first_frame alongside refs
        first_frame_asset_id, continuation_note = await _continuation_frame_asset_id(
            session, project_id, shot
        )
    if (
        first_frame_asset_id is None
        and not reference_urls
        and shot.preferred_model == PreferredModel.I2V.value
    ):
        first_frame_asset_id = await _auto_first_frame_asset_id(session, project_id)
        if first_frame_asset_id:
            continuation_note = "first-frame control from the promoted look frame"
    if reference_urls:
        character = await session.get(CharacterProfile, character_id) if character_id else None
        who = f" ({character.name})" if character else ""
        routing_note = (
            f"r2v — {len(reference_urls)} reference image(s){who} lock subject consistency"
        )
        if continuation_note:
            routing_note += f"; {continuation_note}"
    elif first_frame_asset_id:
        routing_note = f"i2v — {continuation_note or 'first-frame control'}"
    else:
        routing_note = "t2v — text-to-video draft (no references in project memory yet)"

    first_frame_url = (
        await asset_url(session, first_frame_asset_id) if first_frame_asset_id else None
    )

    # --- prompt: compose from project memory (visual brief / style pack / character) ---
    visual_brief = await _scene_visual_brief(session, shot)
    style_pack = await _project_style_pack(session, project_id)
    character = None
    if character_id:
        character = await session.get(CharacterProfile, character_id)
        if character and character.project_id != project_id:
            character = None
    brief_row = (
        (await session.execute(select(Brief).where(Brief.project_id == project_id)))
        .scalars()
        .first()
    )
    prompt = compose_shot_prompt(
        shot,
        visual_brief=visual_brief,
        style_pack=style_pack,
        character=character,
        has_reference_images=bool(reference_urls),
        clarifications=brief_row.clarifications if brief_row else None,
    )
    negative_prompt = compose_negative_prompt(
        visual_brief=visual_brief, style_pack=style_pack, character=character
    )
    if negative_prompt:
        gen_params["negative_prompt"] = negative_prompt

    version = ShotVersion(
        shot_id=shot.id,
        prompt=prompt,
        status=ShotVersionStatus.DRAFT.value,
        routing_note=routing_note,
        gen_params=gen_params,
    )
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
        negative_prompt=negative_prompt,
    )
    version.model = sub.model
    job.task_id = sub.task_id
    job.model = sub.model
    job.started_at = _now()
    job.cost_usd = (
        0.0 if settings.use_mock_video else video_cost_usd(duration, settings.video_resolution)
    )
    log.info(
        "shot.generate project=%s shot=%s model=%s dur=%ss cost=$%.3f refs=%d route=%s",
        project_id,
        shot.id,
        sub.model,
        duration,
        job.cost_usd,
        len(reference_urls),
        routing_note,
    )

    if settings.use_mock_video:
        await _ingest_video_bytes(
            session, project_id, version, MOCK_MP4, use_mock=True, source_model=sub.model
        )
        job.status = JobStatus.SUCCEEDED.value
        job.completed_at = _now()
    else:
        job.status = JobStatus.RUNNING.value

    session.add_all([version, job])
    await session.commit()

    if settings.use_mock_video and settings.auto_review:
        await review_service.review_version_safe(session, version)
    return version, job


async def submit_shot_edit(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    source_version_id: str,
    instruction: str,
    *,
    auth: AuthCtx,
) -> tuple[ShotVersion, GenerationJob]:
    settings = get_settings()
    await assert_within_cap(session, "video", 1, auth=auth)
    source = await session.get(ShotVersion, source_version_id)
    if source is None or source.shot_id != shot.id or not source.output_asset_id:
        raise LookupError("source version has no video to edit")
    source_url = await asset_url(session, source.output_asset_id) or ""

    version = ShotVersion(
        shot_id=shot.id,
        parent_version_id=source_version_id,
        prompt=instruction,
        status=ShotVersionStatus.DRAFT.value,
        routing_note="videoedit — natural-language revision of the parent take",
        gen_params={"instruction": instruction, "source_version_id": source_version_id},
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
        await _ingest_video_bytes(
            session, project_id, version, MOCK_MP4, use_mock=True, source_model=sub.model
        )
        job.status = JobStatus.SUCCEEDED.value
        job.completed_at = _now()
    else:
        job.status = JobStatus.RUNNING.value

    session.add_all([version, job])
    await session.commit()

    if settings.use_mock_video and settings.auto_review:
        await review_service.review_version_safe(session, version)
    return version, job


async def retry_job(
    session: AsyncSession, project_id: str, job: GenerationJob, *, auth: AuthCtx
) -> tuple[ShotVersion, GenerationJob]:
    """Re-run a FAILED job with the exact same direction (a fresh take + fresh job)."""
    if job.status != JobStatus.FAILED.value:
        raise LookupError("only failed jobs can be retried")
    version = await session.get(ShotVersion, job.shot_version_id)
    shot = await session.get(Shot, version.shot_id) if version else None
    if shot is None or shot.project_id != project_id:
        raise LookupError("job not found")
    params = version.gen_params or {}
    if "instruction" in params:
        return await submit_shot_edit(
            session,
            project_id,
            shot,
            params["source_version_id"],
            params["instruction"],
            auth=auth,
        )
    return await submit_shot(
        session,
        project_id,
        shot,
        auth=auth,
        first_frame_asset_id=params.get("first_frame_asset_id"),
        reference_asset_ids=params.get("reference_asset_ids"),
        character_id=params.get("character_id"),
        continue_from_previous=bool(params.get("continue_from_previous")),
    )


async def poll_and_ingest_job(session: AsyncSession, job: GenerationJob) -> GenerationJob:
    if job.status != JobStatus.RUNNING.value:
        return job

    res = await poll_video(job.task_id)
    reviewed_version: ShotVersion | None = None
    if res.status == "SUCCEEDED" and res.video_url and not res.video_url.startswith("mock://"):
        version = await session.get(ShotVersion, job.shot_version_id)
        shot = await session.get(Shot, version.shot_id) if version else None
        project_id = shot.project_id if shot else ""
        data = await download_bytes(res.video_url)
        if version:
            await _ingest_video_bytes(
                session, project_id, version, data, use_mock=False, source_model=job.model or ""
            )
            reviewed_version = version
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

    if reviewed_version is not None and get_settings().auto_review:
        await review_service.review_version_safe(session, reviewed_version)
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
