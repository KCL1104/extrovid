"""Project CRUD."""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import ImageAsset
from app.models.concept import LookFrame, VisualConceptSet
from app.models.director import DirectorTurn
from app.models.gallery import PublishedVideo
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile, StylePack
from app.models.project import Brief, Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.models.source import SourceEvent
from app.models.timeline import TimelineSequence
from app.schemas.api import ProjectCreate, ProjectStats, ProjectUpdate


async def create_project(session: AsyncSession, owner_id: str, data: ProjectCreate) -> Project:
    title = (data.title or "").strip()
    if not title:
        # Auto-name "Project N" where N = owner's existing project count + 1.
        count = (
            await session.execute(
                select(func.count()).select_from(Project).where(Project.owner_id == owner_id)
            )
        ).scalar_one()
        title = f"Project {count + 1}"
    project = Project(
        title=title,
        owner_id=owner_id,
        aspect_ratio=data.aspect_ratio.value,
        target_duration_sec=data.target_duration_sec,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


async def list_projects(
    session: AsyncSession, *, owner_id: str | None, is_admin: bool
) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at.desc())
    if not is_admin:  # admin sees every project; a user sees only their own
        stmt = stmt.where(Project.owner_id == owner_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def stats_for(session: AsyncSession, project_ids: list[str]) -> dict[str, ProjectStats]:
    """Production progress counters per project (grouped counts, four queries total)."""
    if not project_ids:
        return {}
    stats = {pid: ProjectStats() for pid in project_ids}

    for pid, n in await session.execute(
        select(Scene.project_id, func.count())
        .where(Scene.project_id.in_(project_ids))
        .group_by(Scene.project_id)
    ):
        stats[pid].scenes = n
    for pid, n in await session.execute(
        select(Shot.project_id, func.count())
        .where(Shot.project_id.in_(project_ids))
        .group_by(Shot.project_id)
    ):
        stats[pid].shots = n
    for pid, n in await session.execute(
        select(Shot.project_id, func.count(func.distinct(Shot.id)))
        .join(ShotVersion, ShotVersion.shot_id == Shot.id)
        .where(Shot.project_id.in_(project_ids), ShotVersion.output_asset_id.is_not(None))
        .group_by(Shot.project_id)
    ):
        stats[pid].rendered_shots = n
    for pid, n in await session.execute(
        select(TimelineSequence.project_id, func.count())
        .where(TimelineSequence.project_id.in_(project_ids))
        .group_by(TimelineSequence.project_id)
    ):
        stats[pid].cuts = n
    # mean AI dailies score across scored takes — a quick triage signal on the dashboard
    for pid, avg in await session.execute(
        select(Shot.project_id, func.avg(ShotVersion.score))
        .join(ShotVersion, ShotVersion.shot_id == Shot.id)
        .where(Shot.project_id.in_(project_ids), ShotVersion.score.is_not(None))
        .group_by(Shot.project_id)
    ):
        stats[pid].avg_score = round(float(avg), 1) if avg is not None else None
    return stats


async def update_project(session: AsyncSession, project: Project, data: ProjectUpdate) -> Project:
    if data.title is not None:
        project.title = data.title
    if data.status is not None:
        project.status = data.status.value
    if data.aspect_ratio is not None:
        project.aspect_ratio = data.aspect_ratio.value
    if data.target_duration_sec is not None:
        project.target_duration_sec = data.target_duration_sec
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project: Project) -> list[str]:
    """Delete the project + all dependent rows, and RETURN the bucket keys to clean.

    The bucket cleanup is deliberately NOT done here: a media-heavy project (videos, takes,
    thumbnails, keyframes, portraits, cut) can have dozens of objects, and deleting them inline
    made the request outlive the edge-proxy timeout — the browser saw "Failed to fetch" even
    though the DB delete had committed. The caller schedules ``asset_service.delete_objects`` as
    a background task so the response returns immediately.
    """
    pid = project.id
    # Remove dependent rows CHILD-FIRST (no DB-level cascade configured). Order matters —
    # the FK chain is: GenerationJob -> ShotVersion -> Shot; Shot -> LookFrame (via
    # keyframe_frame_id/last_keyframe_frame_id), Scene, CharacterProfile; LookFrame ->
    # VisualConceptSet -> Scene. So shots must go BEFORE look frames, and look frames
    # before concept sets and scenes, or Postgres FKs (shot_keyframe_frame_id_fkey,
    # lookframe_project_id_fkey, …) reject the delete.
    shot_ids = (
        (await session.execute(select(Shot.id).where(Shot.project_id == pid))).scalars().all()
    )
    if shot_ids:
        version_ids = (
            (await session.execute(select(ShotVersion.id).where(ShotVersion.shot_id.in_(shot_ids))))
            .scalars()
            .all()
        )
        if version_ids:
            await session.execute(
                delete(GenerationJob).where(GenerationJob.shot_version_id.in_(version_ids))
            )
        await session.execute(delete(ShotVersion).where(ShotVersion.shot_id.in_(shot_ids)))
    await session.execute(delete(Shot).where(Shot.project_id == pid))
    # ALL look frames by project_id (concept-set frames AND keyframes, concept_set_id=None),
    # now that no shot references them.
    await session.execute(delete(LookFrame).where(LookFrame.project_id == pid))
    await session.execute(delete(VisualConceptSet).where(VisualConceptSet.project_id == pid))
    await session.execute(delete(Scene).where(Scene.project_id == pid))
    await session.execute(delete(Brief).where(Brief.project_id == pid))
    # PublishedVideo (gallery share) FKs the rough cut's TimelineSequence (and the project),
    # so it must go BEFORE the sequence — else published_video_timeline_sequence_id_fkey rejects
    # the delete (a published project would 500 on delete).
    await session.execute(delete(PublishedVideo).where(PublishedVideo.project_id == pid))
    await session.execute(delete(TimelineSequence).where(TimelineSequence.project_id == pid))
    await session.execute(delete(CharacterProfile).where(CharacterProfile.project_id == pid))
    await session.execute(delete(StylePack).where(StylePack.project_id == pid))
    # these also FK the project (long-source import + director chat history)
    await session.execute(delete(SourceEvent).where(SourceEvent.project_id == pid))
    await session.execute(delete(DirectorTurn).where(DirectorTurn.project_id == pid))
    # capture object keys before clearing rows, so we can clean the bucket after commit
    keys = (
        (await session.execute(select(ImageAsset.bucket_key).where(ImageAsset.project_id == pid)))
        .scalars()
        .all()
    )
    await session.execute(delete(ImageAsset).where(ImageAsset.project_id == pid))
    await session.delete(project)
    await session.commit()
    return list(keys)  # caller cleans the bucket off the request path
