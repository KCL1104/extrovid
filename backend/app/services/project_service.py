"""Project CRUD."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import ImageAsset
from app.models.concept import LookFrame, VisualConceptSet
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile, StylePack
from app.models.project import Brief, Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.models.timeline import TimelineSequence
from app.schemas.api import ProjectCreate, ProjectUpdate
from app.services import asset_service


async def create_project(session: AsyncSession, data: ProjectCreate) -> Project:
    project = Project(
        title=data.title,
        owner_id=data.owner_id,
        aspect_ratio=data.aspect_ratio.value,
        target_duration_sec=data.target_duration_sec,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


async def list_projects(session: AsyncSession) -> list[Project]:
    res = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return list(res.scalars().all())


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


async def delete_project(session: AsyncSession, project: Project) -> None:
    pid = project.id
    # remove dependent rows first (no DB-level cascade configured)
    cs_ids = (
        (
            await session.execute(
                select(VisualConceptSet.id).where(VisualConceptSet.project_id == pid)
            )
        )
        .scalars()
        .all()
    )
    if cs_ids:
        await session.execute(delete(LookFrame).where(LookFrame.concept_set_id.in_(cs_ids)))
    await session.execute(delete(VisualConceptSet).where(VisualConceptSet.project_id == pid))
    # ShotVersion/GenerationJob FK to shot/shotversion — clear them before shots.
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
    await session.execute(delete(Scene).where(Scene.project_id == pid))
    await session.execute(delete(Brief).where(Brief.project_id == pid))
    await session.execute(delete(TimelineSequence).where(TimelineSequence.project_id == pid))
    await session.execute(delete(CharacterProfile).where(CharacterProfile.project_id == pid))
    await session.execute(delete(StylePack).where(StylePack.project_id == pid))
    # capture object keys before clearing rows, so we can clean the bucket after commit
    keys = (
        (await session.execute(select(ImageAsset.bucket_key).where(ImageAsset.project_id == pid)))
        .scalars()
        .all()
    )
    await session.execute(delete(ImageAsset).where(ImageAsset.project_id == pid))
    await session.delete(project)
    await session.commit()
    await asset_service.delete_objects(list(keys))  # best-effort bucket cleanup
