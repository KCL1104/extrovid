"""Generate concept images for a VisualConceptSet's look frames and persist them.

Sequential generation (one Qwen-Image call per frame) keeps us within the provider's
image rate limits. Each frame's image_asset_id is filled and the set is marked GENERATED.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx
from app.core.config import get_settings
from app.models.concept import LookFrame, VisualConceptSet
from app.models.enums import ConceptSetStatus
from app.models.memory import CharacterProfile, StylePack
from app.models.project import Project
from app.models.shot import Shot
from app.providers.image_factory import edit_image, generate_image, size_for_aspect
from app.services import review_service
from app.services.asset_service import asset_url, store_image
from app.services.prompt_service import (
    compose_keyframe_prompt,
    compose_negative_prompt,
    portrait_view_for,
)
from app.services.usage_service import assert_within_cap


async def generate_images_for_concept_set(
    session: AsyncSession,
    project_id: str,
    concept_set_id: str,
    *,
    auth: AuthCtx,
    limit: int | None = None,
) -> list[LookFrame]:
    cs = await session.get(VisualConceptSet, concept_set_id)
    if cs is None or cs.project_id != project_id:
        raise LookupError("concept set not found")

    project = await session.get(Project, project_id)
    size = size_for_aspect(project.aspect_ratio if project else "")

    frames = (
        (await session.execute(select(LookFrame).where(LookFrame.concept_set_id == concept_set_id)))
        .scalars()
        .all()
    )
    todo = [f for f in frames if not f.image_asset_id]
    if limit is not None:
        todo = todo[:limit]
    if todo:
        await assert_within_cap(session, "image", len(todo), auth=auth)

    # the scene's negative rules condition image generation natively too
    vb = cs.visual_brief or {}
    negative = "; ".join(str(r) for r in (vb.get("negative_rules") or [])[:6]) or None

    for frame in todo:
        result = await generate_image(frame.prompt, size, negative_prompt=negative)
        asset = await store_image(session, project_id, result, frame.prompt)
        frame.image_asset_id = asset.id
        session.add(frame)

    cs.status = ConceptSetStatus.GENERATED.value
    session.add(cs)
    await session.commit()
    return list(frames)


def _keyframe_edit_instruction(view: str, prompt: str) -> str:
    """Repaint instruction phrased for the portrait VIEW the camera will see.

    A back/profile shot anchored to a FRONT face fights the camera and drives identity
    drift, so the back/side variants drop face-identity language and lock the visible
    attributes (hair, build, wardrobe) instead.
    """
    if view == "back":
        return (
            f"Repaint this character seen from behind into a new scene, based on the "
            f"provided back-view portrait: {prompt} Keep the hair, build, and wardrobe "
            "consistent with the base image; the face is not visible."
        )
    if view == "side":
        return (
            f"Repaint this character in profile into a new scene, based on the provided "
            f"side-view portrait: {prompt} Keep the facial profile, hair, build, and "
            "wardrobe consistent with the base image."
        )
    return (
        f"Repaint this exact character into a new scene: {prompt} "
        "Keep the character's identity (face, hair, build, wardrobe) consistent with the "
        "base image."
    )


async def generate_shot_keyframe(
    session: AsyncSession,
    project_id: str,
    shot: Shot,
    *,
    auth: AuthCtx,
) -> LookFrame:
    """Generate the shot's opening keyframe as an image and point the shot at it.

    With a cast lock + portrait sheet, the keyframe is an identity-preserving EDIT of
    the front portrait (ViMax's base-portrait -> scene-variant move); otherwise plain
    text->image. The result is a LookFrame, so the /refine loop works on it for free.
    """
    project = await session.get(Project, project_id)
    size = size_for_aspect(project.aspect_ratio if project else "")

    visual_brief: dict | None = None
    if shot.scene_id:
        cs = (
            (
                await session.execute(
                    select(VisualConceptSet).where(VisualConceptSet.scene_id == shot.scene_id)
                )
            )
            .scalars()
            .first()
        )
        visual_brief = cs.visual_brief if cs else None
    style_pack = (
        (await session.execute(select(StylePack).where(StylePack.project_id == project_id)))
        .scalars()
        .first()
    )
    character = None
    if shot.character_id:
        character = await session.get(CharacterProfile, shot.character_id)
        if character and character.project_id != project_id:
            character = None

    prompt = compose_keyframe_prompt(
        shot, visual_brief=visual_brief, style_pack=style_pack, character=character
    )
    negative = compose_negative_prompt(
        visual_brief=visual_brief, style_pack=style_pack, character=character
    )

    await assert_within_cap(session, "image", 1, auth=auth)
    # anchor the keyframe to the portrait view the camera will actually see; only edit when
    # that exact view exists — editing a front face into a back/profile shot fights the
    # camera, so a missing view falls back to text->image (the prompt already carries the
    # character description, first_frame_desc, and framing).
    portraits = (character.portrait_assets or {}) if character else {}
    view = portrait_view_for(shot) if character else "front"
    base_id = portraits.get(view)
    base_url = await asset_url(session, base_id) if base_id else None
    if base_url:
        result = await edit_image(base_url, _keyframe_edit_instruction(view, prompt))
    else:
        result = await generate_image(prompt, size, negative_prompt=negative)
    asset = await store_image(session, project_id, result, prompt)

    frame = LookFrame(
        project_id=project_id,
        concept_set_id=None,
        prompt=prompt,
        source_model=result.source_model,
        image_asset_id=asset.id,
        tags=["keyframe", f"shot-{shot.order}"],
    )
    session.add(frame)
    await session.flush()
    shot.keyframe_frame_id = frame.id
    session.add(shot)
    await session.commit()
    await session.refresh(frame)
    # gate the keyframe before any video budget is spent: identity/composition/view verdict
    if get_settings().auto_review:
        await review_service.review_keyframe_safe(session, frame, shot, character)
    return frame


async def refine_look_frame(
    session: AsyncSession,
    project_id: str,
    frame_id: str,
    instruction: str,
    *,
    auth: AuthCtx,
) -> LookFrame:
    """Iteratively refine an existing look frame with Qwen-Image-Edit.

    Creates a NEW LookFrame in the same concept set with ``parent_frame_id`` lineage —
    the original is never overwritten, mirroring the take-lineage pattern on videos.
    """
    frame = await session.get(LookFrame, frame_id)
    if frame is None or frame.project_id != project_id:
        raise LookupError("look frame not found")
    if not frame.image_asset_id:
        raise LookupError("look frame has no image to refine — generate images first")
    source_url = await asset_url(session, frame.image_asset_id)
    if not source_url:
        raise LookupError("look frame image is unavailable")

    await assert_within_cap(session, "image", 1, auth=auth)
    result = await edit_image(source_url, instruction)
    prompt = f"{frame.prompt} — refined: {instruction}"
    asset = await store_image(session, project_id, result, prompt)

    refined = LookFrame(
        project_id=project_id,
        concept_set_id=frame.concept_set_id,
        prompt=prompt,
        source_model=result.source_model,
        image_asset_id=asset.id,
        tags=[*frame.tags, "refined"],
        parent_frame_id=frame.id,
    )
    session.add(refined)
    await session.commit()
    await session.refresh(refined)
    return refined
