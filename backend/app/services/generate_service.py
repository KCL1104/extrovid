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
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import event_bus
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
from app.services.prompt_service import (
    compose_negative_prompt,
    compose_shot_prompt,
    portrait_view_for,
)
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


# Wan r2v accepts up to 5 media items; cap references at 4 so the identity portrait AND a
# first_frame seed (continuation/keyframe anchor) always survive the provider's media limit.
_MAX_REFERENCE_IMAGES = 4


async def _resolve_reference_urls(
    session: AsyncSession,
    project_id: str,
    reference_asset_ids: list[str] | None,
    character_id: str | None,
    shot: Shot | None = None,
) -> list[str]:
    """Resolve reference image URLs in priority tiers, identity portrait first.

    Tier order (highest first): the view-matched character portrait — reserved at slot 0,
    never evicted — then caller-provided references, then up to two character look frames.
    Capped so the identity anchor (and the first_frame seed added downstream) is never
    crowded out by lower-priority references.
    """
    portrait_id: str | None = None
    look_frame_asset_ids: list[str] = []
    if character_id:
        cp = await session.get(CharacterProfile, character_id)
        if cp and cp.project_id == project_id:
            # ONE portrait view, matched to the shot's direction (back view for
            # over-the-shoulder, etc.) — the identity anchor ahead of everything else
            portraits = cp.portrait_assets or {}
            view = portrait_view_for(shot)
            portrait_id = portraits.get(view) or portraits.get("front")
            for fid in cp.reference_look_frame_ids:
                lf = await session.get(LookFrame, fid)
                if lf and lf.image_asset_id:
                    look_frame_asset_ids.append(lf.image_asset_id)

    # priority order: portrait (identity anchor) > caller refs > at most two look frames
    ordered: list[str] = []
    if portrait_id:
        ordered.append(portrait_id)
    ordered.extend(reference_asset_ids or [])
    ordered.extend(look_frame_asset_ids[:2])

    urls: list[str] = []
    for aid in dict.fromkeys(ordered):  # dedupe, preserve priority order
        u = await asset_url(session, aid)
        if u:
            urls.append(u)
        if len(urls) >= _MAX_REFERENCE_IMAGES:
            break
    return urls


async def _previous_shot(session: AsyncSession, project_id: str, shot: Shot) -> Shot | None:
    """The shot immediately before this one by global order (regardless of render state)."""
    return (
        (
            await session.execute(
                select(Shot)
                .where(Shot.project_id == project_id, Shot.order < shot.order)
                .order_by(Shot.order.desc())
            )
        )
        .scalars()
        .first()
    )


async def _continuation_seed(
    session: AsyncSession, project_id: str, shot: Shot
) -> tuple[str, str]:
    """The first-frame seed for a continuation shot. Returns (asset_id, note).

    Prefers the PREVIOUS shot's planned closing keyframe — image-level chaining that needs
    no rendered video, parallelizes, and does not compound drift. Falls back to extracting
    the previous take's rendered last frame only when no closing keyframe exists. Raises
    LookupError when there is nothing to continue from.
    """
    prev = await _previous_shot(session, project_id, shot)
    if prev is None:
        raise LookupError("no previous shot to continue from")

    # 1. planned closing keyframe (preferred — drift-free, no render dependency)
    if prev.last_keyframe_frame_id:
        lf = await session.get(LookFrame, prev.last_keyframe_frame_id)
        if lf and lf.image_asset_id:
            return lf.image_asset_id, f"continues from shot #{prev.order}'s planned last keyframe"

    # 2. fall back to the previous take's rendered last frame
    found = await review_service.previous_shot_take(session, project_id, shot)
    if found is None:
        raise LookupError(
            "previous shot has no closing keyframe or finished take to continue from"
        )
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


async def _continuation_ready(session: AsyncSession, project_id: str, shot: Shot) -> bool:
    """Can this shot's continuation seed be resolved now? True if the previous shot has a
    planned closing keyframe (no render needed) OR a finished take to extract from."""
    prev = await _previous_shot(session, project_id, shot)
    if prev is None:
        return False
    if prev.last_keyframe_frame_id:
        lf = await session.get(LookFrame, prev.last_keyframe_frame_id)
        if lf and lf.image_asset_id:
            return True
    return await review_service.previous_shot_take(session, project_id, shot) is not None


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
    batch_id: str | None = None,
    batch_size: int = 1,
    defer: bool = False,
) -> tuple[ShotVersion, GenerationJob]:
    await assert_within_cap(session, "video", 1, auth=auth)

    if character_id is None:
        # cast lock: the shot's persisted character is the default; an explicit request wins
        character_id = shot.character_id

    gen_params = {
        "first_frame_asset_id": first_frame_asset_id,
        "reference_asset_ids": reference_asset_ids,
        "character_id": character_id,
        "continue_from_previous": continue_from_previous,
    }
    if batch_id:
        gen_params["batch_id"] = batch_id
        gen_params["batch_size"] = batch_size
    if defer:
        gen_params["deferred"] = True

    version = ShotVersion(
        shot_id=shot.id,
        prompt="",
        status=ShotVersionStatus.DRAFT.value,
        routing_note="queued — awaiting the previous shot's take (continuation chain)",
        gen_params=gen_params,
    )
    session.add(version)
    await session.flush()
    job = GenerationJob(
        shot_version_id=version.id, provider="dashscope", status=JobStatus.QUEUED.value
    )
    session.add(job)
    await session.flush()

    if defer:
        # stays QUEUED; the reconciler's dispatch_deferred activates it once the
        # upstream take lands — DB-backed dependencies, restart-safe by construction
        await session.commit()
        return version, job
    return await _activate_submission(session, project_id, shot, version, job)


async def _activate_submission(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    version: ShotVersion,
    job: GenerationJob,
) -> tuple[ShotVersion, GenerationJob]:
    """Resolve references/routing, compose the prompt, and submit to the provider.

    Runs either inline (normal submits) or from the reconciler (deferred chain jobs).
    """
    settings = get_settings()
    params = version.gen_params or {}
    first_frame_asset_id = params.get("first_frame_asset_id")
    reference_asset_ids = params.get("reference_asset_ids")
    character_id = params.get("character_id")
    continue_from_previous = bool(params.get("continue_from_previous"))
    gen_params = dict(params)

    project = await session.get(Project, project_id)
    ratio = _ratio_for(project.aspect_ratio if project else "")
    duration = max(2, min(15, round(shot.duration_sec)))

    reference_urls = await _resolve_reference_urls(
        session, project_id, reference_asset_ids, character_id, shot=shot
    )

    # --- routing: decide the input mode and record why ---
    continuation_note: str | None = None
    if continue_from_previous and first_frame_asset_id is None:
        # the seed composes with references too: r2v accepts a first_frame alongside refs
        first_frame_asset_id, continuation_note = await _continuation_seed(
            session, project_id, shot
        )
    if first_frame_asset_id is None and shot.keyframe_frame_id:
        # the shot's planned keyframe anchors composition + identity (composes with r2v)
        kf = await session.get(LookFrame, shot.keyframe_frame_id)
        if kf and kf.image_asset_id:
            first_frame_asset_id = kf.image_asset_id
            continuation_note = "planned keyframe anchors composition and identity"
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

    version.prompt = prompt
    version.routing_note = routing_note
    version.gen_params = gen_params
    session.add(version)

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
    if settings.use_mock_video:
        await maybe_autoselect_batch(session, version)
    # live: tell subscribed workspaces a take changed state (the 5s poll is the fallback)
    event_bus.publish(
        project_id,
        {"type": "job", "shot_id": shot.id, "version_id": version.id, "status": job.status},
    )
    return version, job


async def submit_shot_batch(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    *,
    auth: AuthCtx,
    num_takes: int,
    first_frame_asset_id: str | None = None,
    reference_asset_ids: list[str] | None = None,
    character_id: str | None = None,
    continue_from_previous: bool = False,
) -> list[tuple[ShotVersion, GenerationJob]]:
    """Best-of-N fan-out: N takes with the same direction (ViMax's unwired selector,
    actually shipped). All-or-nothing cap check up front; siblings share a batch_id so
    the reviewer-driven auto-select can pick a winner once every take lands."""
    await assert_within_cap(session, "video", num_takes, auth=auth)
    batch_id = uuid.uuid4().hex if num_takes > 1 else None
    out: list[tuple[ShotVersion, GenerationJob]] = []
    for _ in range(num_takes):
        out.append(
            await submit_shot(
                session,
                project_id,
                shot,
                auth=auth,
                first_frame_asset_id=first_frame_asset_id,
                reference_asset_ids=reference_asset_ids,
                character_id=character_id,
                continue_from_previous=continue_from_previous,
                batch_id=batch_id,
                batch_size=num_takes,
            )
        )
    return out


async def _has_previous_shot(session: AsyncSession, project_id: str, shot: Shot) -> bool:
    prev = (
        (
            await session.execute(
                select(Shot).where(Shot.project_id == project_id, Shot.order < shot.order)
            )
        )
        .scalars()
        .first()
    )
    return prev is not None


async def submit_scene_batch(
    session: AsyncSession,
    project_id: str,
    shots: list[Shot],
    *,
    auth: AuthCtx,
    continue_from_previous: bool = False,
) -> list[tuple[ShotVersion, GenerationJob]]:
    """Render a whole scene (or project) in one request.

    Without continuation every shot submits immediately — keyframed shots are already
    anchored, so they parallelize freely. With continuation, a shot whose upstream take
    doesn't exist yet is queued as a DEFERRED job; the reconciler activates it when the
    previous shot's take lands (ViMax's frame-event chaining, done as DB rows).
    """
    await assert_within_cap(session, "video", len(shots), auth=auth)
    out: list[tuple[ShotVersion, GenerationJob]] = []
    for shot in sorted(shots, key=lambda s: s.order):
        if not continue_from_previous:
            out.append(await submit_shot(session, project_id, shot, auth=auth))
            continue
        has_prev = await _has_previous_shot(session, project_id, shot)
        if not has_prev:
            # nothing to continue from — the chain's anchor renders directly
            out.append(await submit_shot(session, project_id, shot, auth=auth))
            continue
        # a planned closing keyframe lets the shot render NOW (no wait on the upstream take);
        # otherwise it defers until the previous take lands and its last frame can be read
        ready = await _continuation_ready(session, project_id, shot)
        out.append(
            await submit_shot(
                session,
                project_id,
                shot,
                auth=auth,
                continue_from_previous=True,
                defer=not ready,
            )
        )
    return out


async def dispatch_deferred(session: AsyncSession) -> int:
    """Activate QUEUED chain jobs whose upstream take has landed. Returns count."""
    rows = (
        await session.execute(
            select(GenerationJob, ShotVersion)
            .join(ShotVersion, GenerationJob.shot_version_id == ShotVersion.id)
            .where(GenerationJob.status == JobStatus.QUEUED.value)
        )
    ).all()
    activated = 0
    for job, version in rows:
        if not (version.gen_params or {}).get("deferred"):
            continue
        shot = await session.get(Shot, version.shot_id)
        if shot is None:
            continue
        found = await review_service.previous_shot_take(session, shot.project_id, shot)
        if found is None:
            continue
        try:
            await _activate_submission(session, shot.project_id, shot, version, job)
            activated += 1
        except Exception:  # noqa: BLE001 - one bad chain link must not block the rest
            await session.rollback()
            log.warning("dispatch.failed job=%s", job.id)
    return activated


async def maybe_autoselect_batch(session: AsyncSession, version: ShotVersion) -> None:
    """Once every take of a fan-out batch is terminal, select the best one.

    "Best" = highest review score among passing takes (any scored take as fallback).
    A manual selection anywhere on the shot always wins — we never override the user.
    """
    batch_id = (version.gen_params or {}).get("batch_id")
    if not batch_id:
        return
    batch_size = int((version.gen_params or {}).get("batch_size") or 0)
    shot_versions = (
        (await session.execute(select(ShotVersion).where(ShotVersion.shot_id == version.shot_id)))
        .scalars()
        .all()
    )
    if any(v.selected for v in shot_versions):
        return
    siblings = [v for v in shot_versions if (v.gen_params or {}).get("batch_id") == batch_id]
    if len(siblings) < batch_size:
        return  # batch still being submitted
    terminal = {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}
    for v in siblings:
        job = (
            (
                await session.execute(
                    select(GenerationJob).where(GenerationJob.shot_version_id == v.id)
                )
            )
            .scalars()
            .first()
        )
        if job is None or job.status not in terminal:
            return  # not done yet — a later ingest will re-run this check
    candidates = [v for v in siblings if v.output_asset_id]
    if not candidates:
        return
    passing = [v for v in candidates if (v.review or {}).get("verdict") == "pass"]
    pool = passing or candidates
    winner = max(pool, key=lambda v: v.score if v.score is not None else -1.0)
    for v in shot_versions:
        v.selected = v.id == winner.id
        session.add(v)
    await session.commit()
    log.info(
        "batch.autoselect shot=%s batch=%s winner=%s score=%s",
        version.shot_id,
        batch_id,
        winner.id,
        winner.score,
    )


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
    if job.status in (JobStatus.SUCCEEDED.value, JobStatus.FAILED.value):
        v = await session.get(ShotVersion, job.shot_version_id)
        if v is not None:
            await maybe_autoselect_batch(session, v)
            shot = await session.get(Shot, v.shot_id)
            if shot is not None:
                event_bus.publish(
                    shot.project_id,
                    {"type": "job", "shot_id": shot.id, "version_id": v.id, "status": job.status},
                )
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
    # newly-landed takes may unblock deferred continuation-chain jobs
    try:
        await dispatch_deferred(session)
    except Exception:  # noqa: BLE001
        await session.rollback()
    return len(jobs)
