"""Review-gate endpoints (P1): approve / lock / annotate the plan before generation.

The pipeline pauses at STORYBOARDED; these endpoints turn that pause into a real approval
gate. Generation is blocked for gated tiers until the plan is approved (see ``generation.py``).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.models.enums import AnnotationStatus
from app.models.project import Project
from app.schemas.api import (
    AnnotationCreate,
    AnnotationRead,
    ApproveRequest,
    LockRequest,
)
from app.services import review_gate_service

router = APIRouter(
    prefix="/projects/{project_id}", tags=["review"], dependencies=[Depends(get_owned_project)]
)


@router.post("/plan/approve")
async def approve_plan(
    project_id: str,
    body: ApproveRequest | None = None,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    """Approve the whole plan (empty body) or a subset of scenes/shots. Approving a scene
    approves its shots; the project flips to APPROVED once every scene is approved."""
    body = body or ApproveRequest()
    return await review_gate_service.approve_plan(
        session, project, body.scene_ids, body.shot_ids
    )


@router.get("/plan/cost")
async def plan_cost(project_id: str, session: AsyncSession = Depends(get_session)):
    """Projected spend to render the current plan once (shown at the gate)."""
    return await review_gate_service.projected_cost(session, project_id)


@router.post("/scenes/{scene_id}/lock", response_model=None)
async def lock_scene(
    project_id: str,
    scene_id: str,
    body: LockRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    locked = body.locked if body else True
    try:
        scene = await review_gate_service.set_scene_lock(session, project_id, scene_id, locked)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"id": scene.id, "locked": scene.locked}


@router.post("/shots/{shot_id}/lock", response_model=None)
async def lock_shot(
    project_id: str,
    shot_id: str,
    body: LockRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    locked = body.locked if body else True
    try:
        shot = await review_gate_service.set_shot_lock(session, project_id, shot_id, locked)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"id": shot.id, "locked": shot.locked}


@router.post("/annotations", response_model=AnnotationRead)
async def create_annotation(
    project_id: str, body: AnnotationCreate, session: AsyncSession = Depends(get_session)
):
    ann = await review_gate_service.create_annotation(session, project_id, body)
    return AnnotationRead.model_validate(ann)


@router.get("/annotations", response_model=list[AnnotationRead])
async def list_annotations(
    project_id: str,
    include_resolved: bool = True,
    session: AsyncSession = Depends(get_session),
):
    anns = await review_gate_service.list_annotations(session, project_id, include_resolved)
    return [AnnotationRead.model_validate(a) for a in anns]


@router.post("/annotations/{annotation_id}/resolve", response_model=AnnotationRead)
async def resolve_annotation(
    project_id: str, annotation_id: str, session: AsyncSession = Depends(get_session)
):
    try:
        ann = await review_gate_service.set_annotation_status(
            session, project_id, annotation_id, AnnotationStatus.RESOLVED
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return AnnotationRead.model_validate(ann)
