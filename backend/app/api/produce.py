"""One-click Produce: start / inspect / stop the whole-pipeline orchestration run."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_owned_project
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.project import Project
from app.schemas.api import ProduceRequest
from app.services import produce_service, project_state, review_gate_service

router = APIRouter(prefix="/projects/{project_id}", tags=["produce"])


@router.post("/produce")
async def start_produce(
    project_id: str,
    body: ProduceRequest | None = None,
    project: Project = Depends(get_owned_project),
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Run every remaining stage (portraits -> keyframes -> videos -> voiceovers -> cut).

    Idempotent: each stage only does still-missing work, so calling again resumes a
    paused run. The plan-approval review gate stays authoritative — a gated project
    refuses to start, exactly like the per-stage endpoints."""
    opts = body or ProduceRequest()
    blockers = review_gate_service.project_generation_blockers(project)
    blockers += await review_gate_service.budget_blockers(session, project)
    if blockers:
        raise HTTPException(status_code=409, detail="; ".join(blockers))
    state = await project_state.snapshot(session, project_id)
    if state["shots"] == 0:
        raise HTTPException(status_code=422, detail="no storyboard yet — plan the project first")
    # a factory bound to THIS request's engine, so the background run shares the same DB
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    return produce_service.start(
        project_id,
        auth=auth,
        session_factory=factory,
        mode=opts.mode,
        continue_from_previous=opts.continue_from_previous,
    )


# ponytail: status/stop are DB-free on purpose — the run state lives in memory, and (on
# the test suite's single-connection SQLite) a DB read here would interleave with the
# background run's transactions. The global auth gate still applies; project ids are UUIDs.
@router.get("/produce")
async def produce_status(project_id: str):
    return produce_service.status(project_id)


@router.post("/produce/stop")
async def stop_produce(project_id: str):
    return await produce_service.stop(project_id)
