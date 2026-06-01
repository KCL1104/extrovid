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
from app.providers.image_factory import generate_image, size_for_aspect
from app.services.asset_service import store_image
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

    for frame in todo:
        result = await generate_image(frame.prompt, size)
        asset = await store_image(session, project_id, result, frame.prompt)
        frame.image_asset_id = asset.id
        session.add(frame)

    cs.status = ConceptSetStatus.GENERATED.value
    session.add(cs)
    await session.commit()
    return list(frames)
