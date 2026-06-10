"""Generate concept images for a VisualConceptSet's look frames and persist them.

Sequential generation (one Qwen-Image call per frame) keeps us within the provider's
image rate limits. Each frame's image_asset_id is filled and the set is marked GENERATED.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx
from app.models.concept import LookFrame, VisualConceptSet
from app.models.enums import ConceptSetStatus
from app.models.project import Project
from app.providers.image_factory import edit_image, generate_image, size_for_aspect
from app.services.asset_service import asset_url, store_image
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
