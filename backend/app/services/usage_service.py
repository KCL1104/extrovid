"""Daily usage accounting + per-user cap enforcement for paid generation ops.

Counts come from existing rows scoped to the caller: videos via
GenerationJob → ShotVersion → Shot → Project.owner_id; images via ImageAsset → Project.owner_id.
``owner_id=None`` means the admin/global view (no owner filter). Caps come from the request's
AuthCtx (0 = unlimited). No new tables.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx, CapExceeded
from app.core.logging import log
from app.models.asset import ImageAsset
from app.models.enums import JobStatus
from app.models.generation import GenerationJob, ShotVersion
from app.models.project import Project
from app.models.shot import Shot


def _today_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _scope_videos(stmt, owner_id: str | None):
    """Join a GenerationJob count/sum query up to Project.owner_id when scoping to a user."""
    if owner_id is None:
        return stmt
    return (
        stmt.join(ShotVersion, ShotVersion.id == GenerationJob.shot_version_id)
        .join(Shot, Shot.id == ShotVersion.shot_id)
        .join(Project, Project.id == Shot.project_id)
        .where(Project.owner_id == owner_id)
    )


def _scope_images(stmt, owner_id: str | None):
    if owner_id is None:
        return stmt
    return stmt.join(Project, Project.id == ImageAsset.project_id).where(
        Project.owner_id == owner_id
    )


async def _video_count(session: AsyncSession, owner_id: str | None) -> int:
    stmt = _scope_videos(
        select(func.count())
        .select_from(GenerationJob)
        .where(GenerationJob.started_at >= _today_start()),
        owner_id,
    )
    return int((await session.execute(stmt)).scalar_one())


async def _image_count(session: AsyncSession, owner_id: str | None) -> int:
    stmt = _scope_images(
        select(func.count())
        .select_from(ImageAsset)
        .where(ImageAsset.content_type.like("image/%"), ImageAsset.created_at >= _today_start()),
        owner_id,
    )
    return int((await session.execute(stmt)).scalar_one())


async def _failed_count(session: AsyncSession, owner_id: str | None) -> int:
    stmt = _scope_videos(
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.status == JobStatus.FAILED.value,
            GenerationJob.started_at >= _today_start(),
        ),
        owner_id,
    )
    return int((await session.execute(stmt)).scalar_one())


async def _spend_usd(session: AsyncSession, owner_id: str | None) -> float:
    vstmt = _scope_videos(
        select(func.coalesce(func.sum(GenerationJob.cost_usd), 0.0)).where(
            GenerationJob.started_at >= _today_start()
        ),
        owner_id,
    )
    istmt = _scope_images(
        select(func.coalesce(func.sum(ImageAsset.cost_usd), 0.0)).where(
            ImageAsset.created_at >= _today_start()
        ),
        owner_id,
    )
    video = (await session.execute(vstmt)).scalar_one()
    image = (await session.execute(istmt)).scalar_one()
    return round(float(video) + float(image), 4)


async def usage(session: AsyncSession, auth: AuthCtx) -> dict:
    owner_id = None if auth.is_admin else auth.user_id
    return {
        "videos_today": await _video_count(session, owner_id),
        "images_today": await _image_count(session, owner_id),
        "video_cap": auth.video_cap,
        "image_cap": auth.image_cap,
        "failed_today": await _failed_count(session, owner_id),
        "est_spend_usd": await _spend_usd(session, owner_id),
    }


async def assert_within_cap(session: AsyncSession, kind: str, n: int = 1, *, auth: AuthCtx) -> None:
    cap = auth.video_cap if kind == "video" else auth.image_cap
    if cap <= 0:  # 0 = unlimited (admin, or an explicitly disabled cap)
        return
    owner_id = None if auth.is_admin else auth.user_id
    current = (
        await _video_count(session, owner_id)
        if kind == "video"
        else await _image_count(session, owner_id)
    )
    if current + n > cap:
        log.warning("cap.exceeded kind=%s current=%s cap=%s owner=%s", kind, current, cap, owner_id)
        raise CapExceeded(kind, remaining=max(0, cap - current))
