"""Read reusable production memory (CharacterProfile / StylePack) with resolved thumbnails."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import LookFrame
from app.models.memory import CharacterProfile, StylePack
from app.schemas.api import CharacterRead, StylePackRead
from app.services.asset_service import asset_url


async def _frame_urls(session: AsyncSession, frame_ids: list[str]) -> list[str]:
    urls: list[str] = []
    for fid in frame_ids:
        lf = await session.get(LookFrame, fid)
        if lf and lf.image_asset_id:
            u = await asset_url(session, lf.image_asset_id)
            if u:
                urls.append(u)
    return urls


async def list_characters(session: AsyncSession, project_id: str) -> list[CharacterRead]:
    rows = (
        (
            await session.execute(
                select(CharacterProfile).where(CharacterProfile.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    return [
        CharacterRead(
            id=c.id,
            name=c.name,
            description=c.description,
            reference_image_urls=await _frame_urls(session, c.reference_look_frame_ids),
        )
        for c in rows
    ]


async def list_style_packs(session: AsyncSession, project_id: str) -> list[StylePackRead]:
    rows = (
        (await session.execute(select(StylePack).where(StylePack.project_id == project_id)))
        .scalars()
        .all()
    )
    return [
        StylePackRead(
            id=s.id, label=s.label, image_urls=await _frame_urls(session, s.look_frame_ids)
        )
        for s in rows
    ]
