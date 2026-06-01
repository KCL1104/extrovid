"""Publish / unpublish finished rough cuts to the public gallery + public reads.

Publishing snapshots the project title and the assembled video asset id. A mock (in-memory)
asset can't be served by the public redirect, so publishing one is rejected.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.asset import ImageAsset
from app.models.gallery import PublishedVideo
from app.models.project import Project
from app.models.timeline import TimelineSequence
from app.schemas.api import PublicVideoRead
from app.services.asset_service import presigned_url


def stream_url(published_id: str) -> str:
    return get_settings().backend_base_url.rstrip("/") + f"/api/gallery/{published_id}/video"


def to_read(pv: PublishedVideo) -> PublicVideoRead:
    return PublicVideoRead(
        id=pv.id,
        title=pv.title,
        aspect_ratio=pv.aspect_ratio,
        published_at=pv.published_at,
        stream_url=stream_url(pv.id),
    )


async def is_published(session: AsyncSession, sequence_id: str) -> PublishedVideo | None:
    res = await session.execute(
        select(PublishedVideo).where(PublishedVideo.timeline_sequence_id == sequence_id)
    )
    return res.scalars().first()


async def publish(session: AsyncSession, project: Project, sequence_id: str) -> PublishedVideo:
    seq = await session.get(TimelineSequence, sequence_id)
    if seq is None or seq.project_id != project.id:
        raise LookupError("rough cut not found")
    if not seq.output_asset_id or seq.status != "ready":
        raise ValueError("rough cut is not ready to publish")
    asset = await session.get(ImageAsset, seq.output_asset_id)
    if asset is None:
        raise ValueError("rough cut has no video asset")
    if presigned_url(asset.bucket_key).startswith("mock://"):
        raise ValueError("cannot publish a mock video — generate a real rough cut first")

    existing = await is_published(session, sequence_id)
    if existing:
        return existing
    pv = PublishedVideo(
        project_id=project.id,
        owner_id=project.owner_id,
        timeline_sequence_id=sequence_id,
        output_asset_id=seq.output_asset_id,
        title=project.title,
        aspect_ratio=project.aspect_ratio,
    )
    session.add(pv)
    await session.commit()
    await session.refresh(pv)
    return pv


async def unpublish(session: AsyncSession, project: Project, sequence_id: str) -> None:
    existing = await is_published(session, sequence_id)
    if existing and existing.project_id == project.id:
        await session.delete(existing)
        await session.commit()


async def list_public(
    session: AsyncSession, limit: int = 60, offset: int = 0
) -> list[PublishedVideo]:
    res = await session.execute(
        select(PublishedVideo)
        .order_by(PublishedVideo.published_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(res.scalars().all())


async def get_public(session: AsyncSession, published_id: str) -> PublishedVideo | None:
    return await session.get(PublishedVideo, published_id)
