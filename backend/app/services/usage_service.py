"""Daily usage accounting + cap enforcement for paid generation ops.

Counts come from existing rows: GenerationJob (videos) and ImageAsset (concept images),
filtered to the current UTC day. No new tables.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CapExceeded
from app.core.config import get_settings
from app.core.logging import log
from app.models.asset import ImageAsset
from app.models.enums import JobStatus
from app.models.generation import GenerationJob


def _today_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


async def _video_count(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count())
        .select_from(GenerationJob)
        .where(GenerationJob.started_at >= _today_start())
    )
    return int(res.scalar_one())


async def _image_count(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count())
        .select_from(ImageAsset)
        .where(ImageAsset.content_type.like("image/%"), ImageAsset.created_at >= _today_start())
    )
    return int(res.scalar_one())


async def _failed_count(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.status == JobStatus.FAILED.value,
            GenerationJob.started_at >= _today_start(),
        )
    )
    return int(res.scalar_one())


async def _spend_usd(session: AsyncSession) -> float:
    video = (
        await session.execute(
            select(func.coalesce(func.sum(GenerationJob.cost_usd), 0.0)).where(
                GenerationJob.started_at >= _today_start()
            )
        )
    ).scalar_one()
    image = (
        await session.execute(
            select(func.coalesce(func.sum(ImageAsset.cost_usd), 0.0)).where(
                ImageAsset.created_at >= _today_start()
            )
        )
    ).scalar_one()
    return round(float(video) + float(image), 4)


async def usage(session: AsyncSession) -> dict:
    s = get_settings()
    return {
        "videos_today": await _video_count(session),
        "images_today": await _image_count(session),
        "video_cap": s.daily_video_cap,
        "image_cap": s.daily_image_cap,
        "failed_today": await _failed_count(session),
        "est_spend_usd": await _spend_usd(session),
    }


async def assert_within_cap(session: AsyncSession, kind: str, n: int = 1) -> None:
    s = get_settings()
    if kind == "video":
        cap, current = s.daily_video_cap, await _video_count(session)
    else:
        cap, current = s.daily_image_cap, await _image_count(session)
    if cap > 0 and current + n > cap:
        log.warning("cap.exceeded kind=%s current=%s cap=%s", kind, current, cap)
        raise CapExceeded(kind, remaining=max(0, cap - current))
