"""Promote an approved LookFrame into reusable production memory.

style_pack / character_ref create rows in the (previously reserved) StylePack /
CharacterProfile tables; first_frame / storyboard_card just mark the frame's role.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import LookFrame
from app.models.enums import PromotedAs
from app.models.memory import CharacterProfile, StylePack


async def promote_look_frame(
    session: AsyncSession,
    project_id: str,
    frame_id: str,
    target: PromotedAs,
    name: str | None = None,
) -> dict:
    frame = await session.get(LookFrame, frame_id)
    if frame is None or frame.project_id != project_id:
        raise LookupError("look frame not found")

    frame.promoted_as = target.value
    session.add(frame)
    created: dict = {}

    if target == PromotedAs.STYLE_PACK:
        sp = StylePack(project_id=project_id, label=name or "Style pack", look_frame_ids=[frame_id])
        session.add(sp)
        await session.flush()
        created["style_pack_id"] = sp.id
    elif target == PromotedAs.CHARACTER_REF:
        cp = CharacterProfile(
            project_id=project_id, name=name or "Character", reference_look_frame_ids=[frame_id]
        )
        session.add(cp)
        await session.flush()
        created["character_profile_id"] = cp.id

    await session.commit()
    return {"frame_id": frame_id, "promoted_as": frame.promoted_as, **created}
