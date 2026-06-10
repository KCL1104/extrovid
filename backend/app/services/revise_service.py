"""Targeted revision with a downstream staleness cascade.

Instead of regenerating a whole stage (replace semantics) to change one scene, revise
exactly one artifact and MARK what it invalidates — iteration stays cheap and
invalidation stays visible (ViMax's `_stale_keys_for_revision`, as DB flags).
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.revise_agent import revise_scene_agent, revise_shot_agent, revise_visual_agent
from app.core.logging import log
from app.models.concept import VisualConceptSet
from app.models.scene import Scene
from app.models.shot import Shot
from app.schemas.pipeline import SceneDraft, ShotDTO, VisualBrief


def _revise_prompt(kind: str, current_json: str, instruction: str, scene_order: int) -> str:
    return (
        f"Revise this {kind}. SCENE_ORDER={scene_order}\n"
        f"Current value:\n{current_json}\n"
        f"Instruction: {instruction}"
    )


async def mark_project_stale(session: AsyncSession, project_id: str) -> None:
    """Brief changed without a re-plan: everything planned against it is now stale."""
    for model in (Scene, VisualConceptSet, Shot):
        await session.execute(
            update(model).where(model.project_id == project_id).values(stale=True)
        )


async def revise_scene(
    session: AsyncSession, project_id: str, scene_id: str, instruction: str
) -> Scene:
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise LookupError("scene not found")
    draft = SceneDraft(
        order=scene.order,
        title=scene.title,
        summary=scene.summary,
        beats=scene.beats,
        est_duration_sec=scene.est_duration_sec,
    )
    result = await revise_scene_agent.run(
        _revise_prompt("scene", draft.model_dump_json(), instruction, scene.order)
    )
    revised = result.output
    scene.title = revised.title
    scene.summary = revised.summary
    scene.beats = [b.model_dump(mode="json") for b in revised.beats]
    scene.est_duration_sec = revised.est_duration_sec
    scene.stale = False
    session.add(scene)
    # cascade: this scene's concept set + shots were planned against the OLD scene
    await session.execute(
        update(VisualConceptSet).where(VisualConceptSet.scene_id == scene_id).values(stale=True)
    )
    await session.execute(update(Shot).where(Shot.scene_id == scene_id).values(stale=True))
    await session.commit()
    log.info("revise.scene project=%s scene=%s: %s", project_id, scene_id, instruction[:80])
    return scene


async def revise_visual_brief(
    session: AsyncSession, project_id: str, scene_id: str, instruction: str
) -> VisualConceptSet:
    cs = (
        (
            await session.execute(
                select(VisualConceptSet).where(
                    VisualConceptSet.scene_id == scene_id,
                    VisualConceptSet.project_id == project_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if cs is None or not cs.visual_brief:
        raise LookupError("visual brief not found for that scene")
    current = VisualBrief.model_validate(cs.visual_brief)
    result = await revise_visual_agent.run(
        _revise_prompt(
            "visual brief", current.model_dump_json(), instruction, current.scene_order
        )
    )
    cs.visual_brief = result.output.model_dump(mode="json")
    cs.stale = False
    session.add(cs)
    # shot PROMPTS recompose from the brief at generation time — shots stay fresh;
    # only takes rendered before this revision predate the new direction
    await session.commit()
    log.info("revise.visual project=%s scene=%s: %s", project_id, scene_id, instruction[:80])
    return cs


async def revise_shot(
    session: AsyncSession, project_id: str, shot_id: str, instruction: str
) -> Shot:
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise LookupError("shot not found")
    dto = ShotDTO(
        order=shot.order,
        scene_order=shot.scene_order,
        purpose=shot.purpose,
        duration_sec=shot.duration_sec,
        beat=shot.beat,
        camera_spec=shot.camera_spec,
        performance_spec=shot.performance_spec,
        preferred_model=shot.preferred_model,
        acceptance_rules=shot.acceptance_rules,
        reference_look_frame_ids=shot.reference_look_frame_ids,
        transition=shot.transition,
        framing=shot.framing,
        camera_id=shot.camera_id,
        first_frame_desc=shot.first_frame_desc,
        last_frame_desc=shot.last_frame_desc,
        motion_desc=shot.motion_desc,
        variation_type=shot.variation_type,
    )
    result = await revise_shot_agent.run(
        _revise_prompt("shot", dto.model_dump_json(), instruction, shot.scene_order)
    )
    revised = result.output
    shot.purpose = revised.purpose
    shot.duration_sec = revised.duration_sec
    shot.beat = revised.beat
    shot.camera_spec = revised.camera_spec.model_dump(mode="json")
    shot.performance_spec = revised.performance_spec.model_dump(mode="json")
    shot.preferred_model = revised.preferred_model.value
    shot.acceptance_rules = revised.acceptance_rules
    shot.transition = revised.transition.value
    shot.framing = revised.framing
    shot.first_frame_desc = revised.first_frame_desc
    shot.last_frame_desc = revised.last_frame_desc
    shot.motion_desc = revised.motion_desc
    shot.variation_type = revised.variation_type
    shot.stale = False
    session.add(shot)
    await session.commit()
    log.info("revise.shot project=%s shot=%s: %s", project_id, shot_id, instruction[:80])
    return shot


async def revise(session: AsyncSession, project_id: str, target: str, instruction: str):
    """Dispatch ``target`` of the form 'scene:{id}' | 'visual_brief:{scene_id}' |
    'shot:{id}'. Raises ValueError on malformed targets, LookupError on misses —
    revision targets must be real (ViMax workflow rule)."""
    kind, _, ident = target.partition(":")
    if not ident:
        raise ValueError("target must be 'scene:{id}', 'visual_brief:{scene_id}' or 'shot:{id}'")
    if kind == "scene":
        return await revise_scene(session, project_id, ident, instruction)
    if kind == "visual_brief":
        return await revise_visual_brief(session, project_id, ident, instruction)
    if kind == "shot":
        return await revise_shot(session, project_id, ident, instruction)
    raise ValueError(f"unknown revision target kind: {kind!r}")
