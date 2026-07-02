"""One-click Produce: walk every remaining pipeline stage for a project.

portraits -> keyframes -> shot videos -> voiceovers -> rough cut, reusing the same
idempotent per-stage services the individual buttons call — each stage only does the
work still missing, so re-running Produce resumes wherever the last run stopped
(pause, cap, failure, or server restart). Human control stays in the loop:

- the plan-approval review gate must be open before the API starts a run;
- by default ("gated" mode) a run that CREATED new keyframes pauses there so the board
  can be reviewed before any video budget is spent — Produce again to continue;
- video failures pause the run before audio/cut so takes can be retried first.

Run state is in-memory per process (the DB rows are the durable state — that's what
makes re-running resume correctly); progress is published on the project's event bus
so the workspace /events stream renders it live.
"""

import asyncio
import contextlib

from sqlalchemy import select

from app.core import event_bus
from app.core.auth import AuthCtx, CapExceeded
from app.core.logging import log
from app.models.enums import JobStatus
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.services import (
    audio_service,
    generate_service,
    imagegen_service,
    planning_service,
    portrait_service,
    project_state,
    rough_cut_service,
)

_RUNS: dict[str, asyncio.Task] = {}
_STATUS: dict[str, dict] = {}

_POLL_SEC = 5  # take-landing poll; the reconciler owns provider polling


def status(project_id: str) -> dict:
    st = dict(_STATUS.get(project_id) or {"state": "idle", "stage": None, "detail": None})
    st["running"] = is_running(project_id)
    return st


def is_running(project_id: str) -> bool:
    t = _RUNS.get(project_id)
    return t is not None and not t.done()


def _set(project_id: str, state: str, stage: str | None = None, detail: str | None = None) -> None:
    _STATUS[project_id] = {"state": state, "stage": stage, "detail": detail}
    event_bus.publish(project_id, {"type": "produce", "state": state, "stage": stage, "detail": detail})


def start(
    project_id: str,
    *,
    auth: AuthCtx,
    session_factory,
    mode: str = "gated",
    continue_from_previous: bool = False,
) -> dict:
    """Start (or resume) a produce run. A no-op if one is already running.

    ``session_factory`` is an async_sessionmaker bound to the caller's engine — passed in
    (rather than importing SessionLocal) so the run rides the test suite's per-test engine.
    """
    if is_running(project_id):
        return status(project_id)
    _set(project_id, "running", stage="portraits")
    _RUNS[project_id] = asyncio.create_task(
        _run(
            project_id,
            auth=auth,
            session_factory=session_factory,
            mode=mode,
            continue_from_previous=continue_from_previous,
        )
    )
    return status(project_id)


async def stop(project_id: str) -> dict:
    t = _RUNS.get(project_id)
    if t and not t.done():
        t.cancel()
        # await settlement so the run's DB session is fully closed before we report back
        with contextlib.suppress(BaseException):
            await t
    _set(project_id, "stopped")
    return status(project_id)


async def _shot_needs_video(session, shot: Shot) -> bool:
    """No finished take AND no queued/running job — the idempotence predicate."""
    has_take = (
        (
            await session.execute(
                select(ShotVersion.id)
                .where(ShotVersion.shot_id == shot.id, ShotVersion.output_asset_id.is_not(None))
                .limit(1)
            )
        ).scalar()
        is not None
    )
    if has_take:
        return False
    in_flight = (
        (
            await session.execute(
                select(GenerationJob.id)
                .join(ShotVersion, GenerationJob.shot_version_id == ShotVersion.id)
                .where(
                    ShotVersion.shot_id == shot.id,
                    GenerationJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
                .limit(1)
            )
        ).scalar()
        is not None
    )
    return not in_flight


async def _run(
    project_id: str,
    *,
    auth: AuthCtx,
    session_factory,
    mode: str,
    continue_from_previous: bool,
) -> None:
    SessionLocal = session_factory
    try:
        # --- portraits: every cast member missing a sheet gets one (identity masters) ---
        _set(project_id, "running", stage="portraits")
        async with SessionLocal() as session:
            cast = (
                (
                    await session.execute(
                        select(CharacterProfile).where(CharacterProfile.project_id == project_id)
                    )
                )
                .scalars()
                .all()
            )
            for c in [c for c in cast if not c.portrait_assets]:
                await portrait_service.generate_portrait_sheet(session, project_id, c.id, auth=auth)

        # --- keyframes: opening for every shot, closing for every shot something chains from ---
        _set(project_id, "running", stage="keyframes")
        made_keyframes = 0
        async with SessionLocal() as session:
            shots = await planning_service.list_shots(session, project_id)
            max_order = max((s.order for s in shots), default=-1)
            for shot in shots:
                if not shot.keyframe_frame_id:
                    await imagegen_service.generate_shot_keyframe(session, project_id, shot, auth=auth)
                    made_keyframes += 1
                if shot.order < max_order and shot.last_frame_desc and not shot.last_keyframe_frame_id:
                    await imagegen_service.generate_shot_keyframe(
                        session, project_id, shot, auth=auth, kind="last"
                    )
                    made_keyframes += 1

        if mode == "gated" and made_keyframes:
            _set(
                project_id,
                "paused",
                stage="keyframes",
                detail=(
                    f"{made_keyframes} new keyframe(s) ready — review the board, "
                    "then Produce again to render video"
                ),
            )
            return

        # --- videos: only shots with no finished take and nothing in flight ---
        _set(project_id, "running", stage="videos")
        async with SessionLocal() as session:
            shots = await planning_service.list_shots(session, project_id)
            todo = [s for s in shots if await _shot_needs_video(session, s)]
            if todo:
                await generate_service.submit_scene_batch(
                    session, project_id, todo, auth=auth,
                    continue_from_previous=continue_from_previous,
                )

        # --- wait for takes to land (the reconciler polls the provider; we poll the DB) ---
        while True:
            async with SessionLocal() as session:
                state = await project_state.snapshot(session, project_id)
            if state["jobs_in_flight"] == 0:
                break
            _set(
                project_id,
                "running",
                stage="videos",
                detail=(
                    f"{state['shots_with_take']}/{state['shots']} shots have takes, "
                    f"{state['jobs_in_flight']} job(s) in flight"
                ),
            )
            await asyncio.sleep(_POLL_SEC)
        if state["shots"] and state["shots_with_take"] < state["shots"]:
            _set(
                project_id,
                "paused",
                stage="videos",
                detail=(
                    f"only {state['shots_with_take']}/{state['shots']} shots finished — "
                    "retry the failed jobs, then Produce again"
                ),
            )
            return

        # --- voiceovers: every spoken line still missing audio ---
        _set(project_id, "running", stage="voiceovers")
        async with SessionLocal() as session:
            shots = await planning_service.list_shots(session, project_id)
            for shot in shots:
                if (shot.dialogue or "").strip() and not shot.vo_asset_id:
                    await audio_service.synthesize_shot_voiceover(session, project_id, shot, auth=auth)

        # --- rough cut: always assemble a fresh cut from the selected takes ---
        _set(project_id, "running", stage="rough_cut")
        async with SessionLocal() as session:
            await rough_cut_service.assemble_rough_cut(session, project_id)
        _set(project_id, "done", stage="rough_cut", detail="rough cut assembled")
    except asyncio.CancelledError:
        _set(project_id, "stopped")
        raise
    except CapExceeded as e:
        _set(
            project_id,
            "paused",
            stage=_STATUS.get(project_id, {}).get("stage"),
            detail=(
                f"daily {e.kind} cap: only {e.remaining} left today, fewer than this run needs — "
                "Produce again after it resets"
            ),
        )
    except Exception as e:  # noqa: BLE001 - a produce run must end in a reportable state
        log.warning("produce.failed project=%s", project_id, exc_info=True)
        _set(project_id, "error", stage=_STATUS.get(project_id, {}).get("stage"), detail=str(e))
