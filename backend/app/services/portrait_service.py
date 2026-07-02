"""Canonical multi-view character portraits — the identity anchor for r2v.

ViMax's highest-leverage consistency idea (docs/vimax-research.md B1): one clean,
full-body, white-background front portrait per character, with side and back views
derived from the front view via image EDIT so all three are the same person. Wan r2v
locks identity far better from turnarounds than from busy in-scene look frames, and
the side/back coverage is what saves profile and from-behind shots.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx
from app.core.logging import log
from app.models.memory import CharacterProfile, StylePack
from app.providers.image_factory import edit_image, generate_image
from app.services.asset_service import asset_url, store_image
from app.services.prompt_service import compose_negative_prompt
from app.services.usage_service import assert_within_cap

# Adapted near-verbatim from ViMax's CharacterPortraitsGenerator templates, with an
# explicit lighting + render-quality floor (the portrait is the identity master every
# downstream keyframe/r2v shot anchors to — its quality compounds through the pipeline).
_FRONT_TEMPLATE = (
    "Generate a full-body, front-view portrait of character {name} based on the following "
    "description, with a pure white background. The character should be centered in the "
    "image, occupying most of the frame. Gazing straight ahead. Standing with arms relaxed "
    "at sides. Natural expression.\nFeatures: {features}\nStyle: {style}\n"
    "Lighting: soft, even studio lighting with gentle falloff. "
    "Sharp focus, rich fine detail, professional color grading."
)
_SIDE_INSTRUCTION = (
    "Turn this character to a full side view, facing left, based on the provided front-view "
    "portrait. Keep the character's identity, clothing, and style exactly consistent. "
    "Full body, centered, pure white background."
)
_BACK_INSTRUCTION = (
    "Turn this character to a full back view, based on the provided front-view portrait. "
    "No facial features should be visible. Keep the clothing and style exactly consistent. "
    "Full body, centered, pure white background."
)
_PORTRAIT_SIZE = "928*1664"  # portrait orientation fits a full standing body


def _features(profile: CharacterProfile) -> str:
    bits = [profile.description or ""]
    bits.extend(str(w) for w in profile.wardrobe_rules or [])
    return "; ".join(b for b in bits if b) or "design a distinctive, memorable look"


async def generate_portrait_sheet(
    session: AsyncSession,
    project_id: str,
    character_id: str,
    *,
    auth: AuthCtx,
) -> CharacterProfile:
    """Generate {front, side, back} portraits and store them on the profile.

    Front is text->image; side/back are image-edits OF the front so the set is
    self-consistent. Costs 3 against the image cap. Re-running replaces the sheet.
    """
    profile = await session.get(CharacterProfile, character_id)
    if profile is None or profile.project_id != project_id:
        raise LookupError("character not found")

    style_pack = (
        (await session.execute(select(StylePack).where(StylePack.project_id == project_id)))
        .scalars()
        .first()
    )
    style = (style_pack.visual_style if style_pack else None) or "clean, neutral studio look"

    await assert_within_cap(session, "image", 3, auth=auth)

    front_prompt = _FRONT_TEMPLATE.format(name=profile.name, features=_features(profile), style=style)
    negative = compose_negative_prompt(style_pack=style_pack, character=profile)
    front = await generate_image(front_prompt, _PORTRAIT_SIZE, negative_prompt=negative)
    front_asset = await store_image(
        session, project_id, front, f"portrait front — {profile.name}"
    )

    front_url = await asset_url(session, front_asset.id) or ""
    side = await edit_image(front_url, _SIDE_INSTRUCTION, negative_prompt=negative)
    side_asset = await store_image(session, project_id, side, f"portrait side — {profile.name}")
    back = await edit_image(front_url, _BACK_INSTRUCTION, negative_prompt=negative)
    back_asset = await store_image(session, project_id, back, f"portrait back — {profile.name}")

    profile.portrait_assets = {
        "front": front_asset.id,
        "side": side_asset.id,
        "back": back_asset.id,
    }
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    log.info(
        "portraits.generated project=%s character=%s (%s)", project_id, profile.id, profile.name
    )
    return profile
