"""Planning pipeline endpoints: per-stage generation + the full Brief->Storyboard run.

Each per-stage endpoint generates and persists its slice (replace semantics). ``/run`` runs
the whole pipeline and persists everything atomically — this is the Phase-0 exit endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.models.concept import VisualConceptSet
from app.models.enums import ProjectStatus
from app.models.project import Project
from app.pipeline import orchestrator
from app.schemas.api import ClarifyResult, RunRequest, StoryboardRequest, VisualPlansResponse
from app.schemas.pipeline import (
    BriefInput,
    PipelineResult,
    ScriptDraft,
    Storyboard,
    VisualBrief,
)
from app.schemas.api import ImportSourceRequest, ReviseRequest
from app.services import (
    memory_service,
    planning_service,
    project_state,
    revise_service,
    source_service,
)

router = APIRouter(
    prefix="/projects/{project_id}", tags=["pipeline"], dependencies=[Depends(get_owned_project)]
)


@router.post("/clarify", response_model=ClarifyResult)
async def clarify_brief(project_id: str, body: RunRequest):
    """Assess the raw idea and propose director Q&A. Stateless — nothing is persisted."""
    return await orchestrator.run_clarify(body.raw_prompt)


@router.post("/brief", response_model=BriefInput)
async def generate_brief(
    project_id: str, body: RunRequest, session: AsyncSession = Depends(get_session)
):
    brief = await orchestrator.run_brief(body.raw_prompt, body.clarifications)
    await planning_service.replace_brief(session, project_id, brief, body.clarifications)
    # a changed brief invalidates everything planned against the old one
    await revise_service.mark_project_stale(session, project_id)
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
    clar = await planning_service.stored_clarifications(session, project_id)
    script = await orchestrator.run_script(brief, clar)
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
    clar = await planning_service.stored_clarifications(session, project_id)
    plans = [await orchestrator.run_visual_plan(scene, clar) for scene in script.scenes]
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
    clar = await planning_service.stored_clarifications(session, project_id)
    cast = await planning_service.stored_cast(session, project_id)
    storyboard = await orchestrator.run_storyboard(
        body.script, visual_briefs, body.concept_specs, body.target_duration_sec, clar, cast
    )
    mapping = {s.order: s.id for s in await planning_service.list_scenes(session, project_id)}
    names = await memory_service.character_id_by_name(session, project_id)
    await planning_service.replace_shots(session, project_id, storyboard, mapping, names)
    project = await session.get(Project, project_id)
    if project:
        project.status = ProjectStatus.STORYBOARDED.value
        session.add(project)
    await session.commit()
    return storyboard


@router.post("/import-source")
async def import_source(
    project_id: str, body: ImportSourceRequest, session: AsyncSession = Depends(get_session)
):
    """Import a long narrative source (script/novel/transcript): compression ->
    autoregressive event extraction (resumable) -> scenes + cast. The result lands as
    the project's script; visual dev and storyboard stages run on it as usual."""
    if body.replace:
        await source_service.clear_source(session, project_id)
    return await source_service.import_source(session, project_id, body.text)


@router.get("/source-events")
async def list_source_events(project_id: str, session: AsyncSession = Depends(get_session)):
    events = await source_service.list_events(session, project_id)
    return [
        {
            "index": e.index,
            "description": e.description,
            "process_chain": e.process_chain,
            "is_last": e.is_last,
        }
        for e in events
    ]


@router.get("/state")
async def project_snapshot(project_id: str, session: AsyncSession = Depends(get_session)):
    """Deterministic project checklist — what exists, what's missing, what's stale."""
    return await project_state.snapshot(session, project_id)


@router.post("/revise")
async def revise_artifact(
    project_id: str, body: ReviseRequest, session: AsyncSession = Depends(get_session)
):
    """Targeted revision of ONE artifact ('scene:{id}' | 'visual_brief:{scene_id}' |
    'shot:{id}') with a downstream staleness cascade — no whole-stage regeneration.

    ``dry_run`` returns a non-destructive before/after proposal (the review-gate diff)
    without committing; the caller commits by re-POSTing with ``dry_run=false``."""
    try:
        if body.dry_run:
            proposal = await revise_service.propose(
                session, project_id, body.target, body.instruction
            )
            return {"target": body.target, "dry_run": True, **proposal}
        revised = await revise_service.revise(session, project_id, body.target, body.instruction)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"target": body.target, "revised": revised.model_dump(mode="json")}


@router.post("/run", response_model=PipelineResult)
async def run_full_pipeline(
    body: RunRequest,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    result = await orchestrator.run_pipeline(
        BriefInput(raw_prompt=body.raw_prompt), clarifications=body.clarifications
    )
    await planning_service.persist_pipeline(session, project, result, body.clarifications)
    return result
