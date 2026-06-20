"""Review gate (P1): plan approval, element lock, anchored annotations, cost estimate.

The pipeline pauses at ``STORYBOARDED`` (= awaiting review). For gated tiers (MEDIUM/LONG)
generation is blocked until the human approves the plan; SHORT stays one-prompt-to-video and
is never gated. Annotations anchor review notes to scenes/shots/briefs and a ``change`` note
maps 1:1 onto a ``revise_service`` target.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tiers import Tier, tier_for
from app.core import pricing
from app.core.config import get_settings
from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus, ProjectStatus
from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.schemas.api import AnnotationCreate


def is_gated(project: Project) -> bool:
    """MEDIUM and LONG require human sign-off before generation; SHORT does not."""
    return tier_for(project.target_duration_sec) is not Tier.SHORT


def project_generation_blockers(project: Project) -> list[str]:
    """Empty when the project may generate; otherwise the reasons it can't."""
    if is_gated(project) and project.status != ProjectStatus.APPROVED.value:
        return ["plan not approved"]
    return []


def _element_blockers(project: Project, *, approved: bool) -> list[str]:
    if not is_gated(project):
        return []
    if project.status == ProjectStatus.APPROVED.value or approved:
        return []
    return ["plan not approved"]


def scene_generation_blockers(project: Project, scene: Scene | None) -> list[str]:
    return _element_blockers(project, approved=bool(scene and scene.approved))


def shot_generation_blockers(project: Project, shot: Shot | None) -> list[str]:
    return _element_blockers(project, approved=bool(shot and shot.approved))


async def _scene_count(session: AsyncSession, project_id: str, *, only_unapproved: bool) -> int:
    stmt = select(func.count()).select_from(Scene).where(Scene.project_id == project_id)
    if only_unapproved:
        stmt = stmt.where(Scene.approved.is_(False))
    return int((await session.execute(stmt)).scalar() or 0)


async def approve_plan(
    session: AsyncSession,
    project: Project,
    scene_ids: list[str] | None = None,
    shot_ids: list[str] | None = None,
) -> dict:
    """Approve the whole plan (both lists omitted) or a subset. Approving a scene approves its
    shots too. The project flips to APPROVED once every scene is approved."""
    now = datetime.now(UTC).replace(tzinfo=None)
    whole = scene_ids is None and shot_ids is None
    if whole:
        await session.execute(
            update(Scene).where(Scene.project_id == project.id).values(approved=True, approved_at=now)
        )
        await session.execute(
            update(Shot).where(Shot.project_id == project.id).values(approved=True, approved_at=now)
        )
    else:
        if scene_ids:
            await session.execute(
                update(Scene)
                .where(Scene.project_id == project.id, Scene.id.in_(scene_ids))
                .values(approved=True, approved_at=now)
            )
            await session.execute(
                update(Shot)
                .where(Shot.project_id == project.id, Shot.scene_id.in_(scene_ids))
                .values(approved=True, approved_at=now)
            )
        if shot_ids:
            await session.execute(
                update(Shot)
                .where(Shot.project_id == project.id, Shot.id.in_(shot_ids))
                .values(approved=True, approved_at=now)
            )

    total = await _scene_count(session, project.id, only_unapproved=False)
    unapproved = await _scene_count(session, project.id, only_unapproved=True)
    if total > 0 and unapproved == 0:
        project.status = ProjectStatus.APPROVED.value
        session.add(project)
    await session.commit()
    return {
        "project_status": project.status,
        "scenes_total": total,
        "scenes_unapproved": unapproved,
        "approved": total > 0 and unapproved == 0,
    }


async def set_scene_lock(session: AsyncSession, project_id: str, scene_id: str, locked: bool) -> Scene:
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise LookupError("scene not found")
    scene.locked = locked
    session.add(scene)
    await session.commit()
    return scene


async def set_shot_lock(session: AsyncSession, project_id: str, shot_id: str, locked: bool) -> Shot:
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise LookupError("shot not found")
    shot.locked = locked
    session.add(shot)
    await session.commit()
    return shot


# --------------------------------------------------------------------------- #
# annotations
# --------------------------------------------------------------------------- #


async def create_annotation(
    session: AsyncSession, project_id: str, body: AnnotationCreate
) -> Annotation:
    ann = Annotation(
        project_id=project_id,
        target_kind=body.target_kind.value,
        target_id=body.target_id,
        field=body.field,
        intent=body.intent.value,
        text=body.text,
    )
    session.add(ann)
    await session.commit()
    await session.refresh(ann)
    return ann


async def list_annotations(
    session: AsyncSession, project_id: str, include_resolved: bool = True
) -> list[Annotation]:
    stmt = select(Annotation).where(Annotation.project_id == project_id)
    if not include_resolved:
        stmt = stmt.where(Annotation.status != AnnotationStatus.RESOLVED.value)
    stmt = stmt.order_by(Annotation.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def set_annotation_status(
    session: AsyncSession, project_id: str, annotation_id: str, status: AnnotationStatus
) -> Annotation:
    ann = await session.get(Annotation, annotation_id)
    if ann is None or ann.project_id != project_id:
        raise LookupError("annotation not found")
    ann.status = status.value
    session.add(ann)
    await session.commit()
    await session.refresh(ann)
    return ann


# --------------------------------------------------------------------------- #
# cost estimate (shown at the gate before any money is spent)
# --------------------------------------------------------------------------- #


async def projected_cost(session: AsyncSession, project_id: str) -> dict:
    """Projected spend to render the current plan once at N=1: one video per shot + one
    keyframe image per shot + one TTS line per shot that carries dialogue."""
    settings = get_settings()
    shots = (
        (await session.execute(select(Shot).where(Shot.project_id == project_id))).scalars().all()
    )
    video = sum(pricing.video_cost_usd(s.duration_sec, settings.video_resolution) for s in shots)
    image = len(shots) * pricing.image_cost_usd(settings.qwen_image_model)
    tts = sum(pricing.tts_cost_usd() for s in shots if s.dialogue)
    total = video + image + tts
    return {
        "shots": len(shots),
        "video_usd": round(video, 2),
        "image_usd": round(image, 2),
        "tts_usd": round(tts, 2),
        "total_usd": round(total, 2),
    }
