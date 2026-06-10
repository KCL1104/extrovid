"""Deterministic project snapshot + dependency gating.

The DB-derived equivalent of ViMax's per-turn artifact checklist
(docs/vimax-research.md D1): a compact, machine-readable state block that grounds the
DirectorAgent every turn, drives UI stage gating, and lets generation/assembly
endpoints report precise missing dependencies instead of generic 400s.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import VisualConceptSet
from app.models.enums import JobStatus
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile, StylePack
from app.models.project import Brief, Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.models.timeline import TimelineSequence


async def _count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar() or 0)


async def snapshot(session: AsyncSession, project_id: str) -> dict:
    """Pure DB reads, no LLM. Everything an agent (or the UI) needs to know what
    exists, what's missing, what's stale, and what's still in flight."""
    project = await session.get(Project, project_id)
    has_brief = (
        (await session.execute(select(Brief).where(Brief.project_id == project_id)))
        .scalars()
        .first()
        is not None
    )
    scenes = await _count(
        session, select(func.count()).select_from(Scene).where(Scene.project_id == project_id)
    )
    stale_scenes = await _count(
        session,
        select(func.count())
        .select_from(Scene)
        .where(Scene.project_id == project_id, Scene.stale.is_(True)),
    )
    concept_sets = await _count(
        session,
        select(func.count())
        .select_from(VisualConceptSet)
        .where(VisualConceptSet.project_id == project_id),
    )
    shots = await _count(
        session, select(func.count()).select_from(Shot).where(Shot.project_id == project_id)
    )
    stale_shots = await _count(
        session,
        select(func.count())
        .select_from(Shot)
        .where(Shot.project_id == project_id, Shot.stale.is_(True)),
    )
    shots_with_keyframe = await _count(
        session,
        select(func.count())
        .select_from(Shot)
        .where(Shot.project_id == project_id, Shot.keyframe_frame_id.is_not(None)),
    )
    shots_with_take = await _count(
        session,
        select(func.count(func.distinct(ShotVersion.shot_id)))
        .select_from(ShotVersion)
        .join(Shot, ShotVersion.shot_id == Shot.id)
        .where(Shot.project_id == project_id, ShotVersion.output_asset_id.is_not(None)),
    )
    shots_with_selected = await _count(
        session,
        select(func.count(func.distinct(ShotVersion.shot_id)))
        .select_from(ShotVersion)
        .join(Shot, ShotVersion.shot_id == Shot.id)
        .where(Shot.project_id == project_id, ShotVersion.selected.is_(True)),
    )
    jobs_in_flight = await _count(
        session,
        select(func.count())
        .select_from(GenerationJob)
        .join(ShotVersion, GenerationJob.shot_version_id == ShotVersion.id)
        .join(Shot, ShotVersion.shot_id == Shot.id)
        .where(
            Shot.project_id == project_id,
            GenerationJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        ),
    )
    failed_jobs = await _count(
        session,
        select(func.count())
        .select_from(GenerationJob)
        .join(ShotVersion, GenerationJob.shot_version_id == ShotVersion.id)
        .join(Shot, ShotVersion.shot_id == Shot.id)
        .where(Shot.project_id == project_id, GenerationJob.status == JobStatus.FAILED.value),
    )
    characters = (
        (
            await session.execute(
                select(CharacterProfile).where(CharacterProfile.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    style_packs = await _count(
        session,
        select(func.count()).select_from(StylePack).where(StylePack.project_id == project_id),
    )
    rough_cuts = await _count(
        session,
        select(func.count())
        .select_from(TimelineSequence)
        .where(TimelineSequence.project_id == project_id),
    )
    return {
        "project_status": project.status if project else None,
        "target_duration_sec": project.target_duration_sec if project else None,
        "has_brief": has_brief,
        "scenes": scenes,
        "stale_scenes": stale_scenes,
        "concept_sets": concept_sets,
        "shots": shots,
        "stale_shots": stale_shots,
        "shots_with_keyframe": shots_with_keyframe,
        "shots_with_take": shots_with_take,
        "shots_with_selected_take": shots_with_selected,
        "jobs_in_flight": jobs_in_flight,
        "failed_jobs": failed_jobs,
        "characters": [
            {
                "name": c.name,
                "has_portraits": bool(c.portrait_assets),
                "has_references": bool(c.reference_look_frame_ids),
            }
            for c in characters
        ],
        "style_packs": style_packs,
        "rough_cuts": rough_cuts,
    }


def missing_for(state: dict, action: str) -> list[str]:
    """What an action still needs — report missing dependencies instead of pretending
    work started (ViMax's render gate)."""
    missing: list[str] = []
    if action in ("generate", "rough_cut") and state["shots"] == 0:
        missing.append("storyboard")
    if action == "rough_cut" and state["shots_with_take"] == 0:
        missing.append("finished takes")
    return missing
