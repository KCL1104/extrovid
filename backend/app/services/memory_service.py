"""Read/write reusable production memory (CharacterProfile / StylePack)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import LookFrame
from app.models.memory import CharacterProfile, StylePack
from app.schemas.api import CharacterRead, StylePackRead
from app.schemas.pipeline import CastMember
from app.services.asset_service import asset_url


async def upsert_cast(
    session: AsyncSession, project_id: str, cast: list[CastMember]
) -> list[CharacterProfile]:
    """Fold an extracted cast into CharacterProfile rows by canonical name.

    Existing profiles (e.g. created via promote) keep their reference frames and
    portraits — only the planned features are refreshed. Caller owns commit.
    """
    rows = (
        (
            await session.execute(
                select(CharacterProfile).where(CharacterProfile.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    by_name = {r.name.strip().lower(): r for r in rows}
    out: list[CharacterProfile] = []
    for member in cast:
        existing = by_name.get(member.name.strip().lower())
        if existing:
            existing.description = member.static_features
            existing.wardrobe_rules = [member.dynamic_features]
            session.add(existing)
            out.append(existing)
        else:
            cp = CharacterProfile(
                project_id=project_id,
                name=member.name,
                description=member.static_features,
                wardrobe_rules=[member.dynamic_features],
            )
            session.add(cp)
            out.append(cp)
    await session.flush()
    return out


async def character_id_by_name(session: AsyncSession, project_id: str) -> dict[str, str]:
    """Lowercased canonical name -> profile id (the automatic cast-lock lookup)."""
    rows = (
        (
            await session.execute(
                select(CharacterProfile).where(CharacterProfile.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    return {r.name.strip().lower(): r.id for r in rows}


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
    out = []
    for c in rows:
        portraits: dict[str, str] = {}
        for view, aid in (c.portrait_assets or {}).items():
            u = await asset_url(session, aid)
            if u:
                portraits[view] = u
        out.append(
            CharacterRead(
                id=c.id,
                name=c.name,
                description=c.description,
                reference_image_urls=await _frame_urls(session, c.reference_look_frame_ids),
                wardrobe_rules=[str(w) for w in c.wardrobe_rules or []],
                portrait_image_urls=portraits,
            )
        )
    return out


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
