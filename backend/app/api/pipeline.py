"""Planning pipeline endpoints: per-stage generation + the full Brief->Storyboard run.

Each per-stage endpoint generates and persists its slice (replace semantics). ``/run`` runs
the whole pipeline and persists everything atomically — this is the Phase-0 exit endpoint.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.models.concept import VisualConceptSet
from app.models.enums import ProjectStatus
from app.models.project import Project
from app.pipeline import orchestrator
from app.schemas.api import RunRequest, StoryboardRequest, VisualPlansResponse
from app.schemas.pipeline import (
    BriefInput,
    PipelineResult,
    ScriptDraft,
    Storyboard,
    VisualBrief,
)
from app.services import planning_service

router = APIRouter(
    prefix="/projects/{project_id}", tags=["pipeline"], dependencies=[Depends(get_owned_project)]
)


@router.post("/brief", response_model=BriefInput)
async def generate_brief(
    project_id: str, body: RunRequest, session: AsyncSession = Depends(get_session)
):
    brief = await orchestrator.run_brief(body.raw_prompt)
    await planning_service.replace_brief(session, project_id, brief)
    # the parsed brief drives the project's framing (mirrors /run's persist_pipeline)
    project = await session.get(Project, project_id)
    if project:
        project.aspect_ratio = brief.aspect_ratio.value
        project.target_duration_sec = brief.target_duration_sec
        session.add(project)
    await session.commit()
    return brief


@router.post("/script", response_model=ScriptDraft)
async def generate_script(
    project_id: str, brief: BriefInput, session: AsyncSession = Depends(get_session)
):
    script = await orchestrator.run_script(brief)
    await planning_service.replace_scenes(session, project_id, script)
    project = await session.get(Project, project_id)
    if project and project.status == ProjectStatus.DRAFT.value:
        project.status = ProjectStatus.SCRIPTED.value
        session.add(project)
    await session.commit()
    return script


@router.post("/visual-briefs", response_model=VisualPlansResponse)
async def generate_visual_briefs(
    project_id: str, script: ScriptDraft, session: AsyncSession = Depends(get_session)
):
    plans = [await orchestrator.run_visual_plan(scene) for scene in script.scenes]
    visual_briefs = [p.visual_brief for p in plans]
    concept_specs = [p.concept_set for p in plans]

    mapping = {s.order: s.id for s in await planning_service.list_scenes(session, project_id)}
    await planning_service.replace_concept_sets(
        session, project_id, concept_specs, mapping, visual_briefs
    )
    await session.commit()
    return VisualPlansResponse(visual_briefs=visual_briefs, concept_specs=concept_specs)


@router.post("/storyboard", response_model=Storyboard)
async def generate_storyboard(
    project_id: str, body: StoryboardRequest, session: AsyncSession = Depends(get_session)
):
    # feed the persisted per-scene art direction into shot planning
    rows = (
        (
            await session.execute(
                select(VisualConceptSet).where(
                    VisualConceptSet.project_id == project_id,
                    VisualConceptSet.visual_brief.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    visual_briefs = [VisualBrief.model_validate(r.visual_brief) for r in rows]
    storyboard = await orchestrator.run_storyboard(
        body.script, visual_briefs, body.concept_specs, body.target_duration_sec
    )
    mapping = {s.order: s.id for s in await planning_service.list_scenes(session, project_id)}
    await planning_service.replace_shots(session, project_id, storyboard, mapping)
    project = await session.get(Project, project_id)
    if project:
        project.status = ProjectStatus.STORYBOARDED.value
        session.add(project)
    await session.commit()
    return storyboard


@router.post("/run", response_model=PipelineResult)
async def run_full_pipeline(
    body: RunRequest,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    result = await orchestrator.run_pipeline(BriefInput(raw_prompt=body.raw_prompt))
    await planning_service.persist_pipeline(session, project, result)
    return result
