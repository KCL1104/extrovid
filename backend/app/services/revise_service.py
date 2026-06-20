"""Targeted revision with a downstream staleness cascade.

Instead of regenerating a whole stage (replace semantics) to change one scene, revise
exactly one artifact and MARK what it invalidates — iteration stays cheap and
invalidation stays visible (ViMax's `_stale_keys_for_revision`, as DB flags).
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.revise_agent import revise_scene_agent, revise_shot_agent, revise_visual_agent
from app.core.agent_run import run_agent
from app.core.logging import log
from app.models.concept import VisualConceptSet
from app.models.enums import ProjectStatus
from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.schemas.pipeline import SceneDraft, ShotDTO, VisualBrief


async def _demote_if_approved(session: AsyncSession, project_id: str) -> None:
    """Editing a scene/shot after the plan was signed off invalidates that sign-off — drop the
    project back to STORYBOARDED so generation re-gates until the user approves again."""
    project = await session.get(Project, project_id)
    if project and project.status == ProjectStatus.APPROVED.value:
        project.status = ProjectStatus.STORYBOARDED.value
        session.add(project)


async def _regate_scene(session: AsyncSession, project_id: str, scene_id: str) -> None:
    """A changed scene art-direction invalidates the human sign-off: un-approve the scene and
    its shots and demote the project so a gated tier re-gates. Does NOT mark shots stale —
    callers that need the staleness cascade do it themselves."""
    await session.execute(
        update(Scene).where(Scene.id == scene_id).values(approved=False, approved_at=None)
    )
    await session.execute(
        update(Shot).where(Shot.scene_id == scene_id).values(approved=False, approved_at=None)
    )
    await _demote_if_approved(session, project_id)


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
    if scene.locked:
        raise ValueError("scene is locked; unlock it before revising")
    draft = SceneDraft(
        order=scene.order,
        title=scene.title,
        summary=scene.summary,
        beats=scene.beats,
        est_duration_sec=scene.est_duration_sec,
    )
    result = await run_agent(
        revise_scene_agent,
        _revise_prompt("scene", draft.model_dump_json(), instruction, scene.order),
    )
    revised = result.output
    scene.title = revised.title
    scene.summary = revised.summary
    scene.beats = [b.model_dump(mode="json") for b in revised.beats]
    scene.est_duration_sec = revised.est_duration_sec
    scene.stale = False
    # a changed scene needs re-approval at the gate
    scene.approved = False
    scene.approved_at = None
    session.add(scene)
    # cascade: this scene's concept set + shots were planned against the OLD scene
    await session.execute(
        update(VisualConceptSet).where(VisualConceptSet.scene_id == scene_id).values(stale=True)
    )
    await session.execute(
        update(Shot).where(Shot.scene_id == scene_id).values(stale=True, approved=False)
    )
    await _demote_if_approved(session, project_id)
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
    result = await run_agent(
        revise_visual_agent,
        _revise_prompt(
            "visual brief", current.model_dump_json(), instruction, current.scene_order
        ),
    )
    cs.visual_brief = result.output.model_dump(mode="json")
    cs.stale = False
    session.add(cs)
    # shot PROMPTS recompose from the brief at generation time — shots stay FRESH (not marked
    # stale, so existing takes aren't forced to re-render). But the art direction that will
    # render changed, so the human sign-off is invalid: un-approve the scene + its shots and
    # demote the project so a gated tier re-gates.
    await _regate_scene(session, project_id, scene_id)
    await session.commit()
    log.info("revise.visual project=%s scene=%s: %s", project_id, scene_id, instruction[:80])
    return cs


async def revise_shot(
    session: AsyncSession, project_id: str, shot_id: str, instruction: str
) -> Shot:
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise LookupError("shot not found")
    if shot.locked:
        raise ValueError("shot is locked; unlock it before revising")
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
    result = await run_agent(
        revise_shot_agent,
        _revise_prompt("shot", dto.model_dump_json(), instruction, shot.scene_order),
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
    # a changed shot needs re-approval at the gate
    shot.approved = False
    shot.approved_at = None
    if shot.scene_id:  # a changed shot invalidates its parent scene's sign-off too
        await session.execute(
            update(Scene).where(Scene.id == shot.scene_id).values(approved=False, approved_at=None)
        )
    session.add(shot)
    await _demote_if_approved(session, project_id)
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


# --------------------------------------------------------------------------- #
# non-destructive proposals (dry-run) — the before/after diff for the review UI
# --------------------------------------------------------------------------- #


async def _propose_scene(session, project_id, scene_id, instruction) -> dict:
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise LookupError("scene not found")
    before = {
        "title": scene.title,
        "summary": scene.summary,
        "beats": scene.beats,
        "est_duration_sec": scene.est_duration_sec,
    }
    draft = SceneDraft(
        order=scene.order,
        title=scene.title,
        summary=scene.summary,
        beats=scene.beats,
        est_duration_sec=scene.est_duration_sec,
    )
    result = await run_agent(
        revise_scene_agent,
        _revise_prompt("scene", draft.model_dump_json(), instruction, scene.order),
    )
    r = result.output
    after = {
        "title": r.title,
        "summary": r.summary,
        "beats": [b.model_dump(mode="json") for b in r.beats],
        "est_duration_sec": r.est_duration_sec,
    }
    return {"kind": "scene", "before": before, "after": after}


async def _propose_visual_brief(session, project_id, scene_id, instruction) -> dict:
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
    result = await run_agent(
        revise_visual_agent,
        _revise_prompt("visual brief", current.model_dump_json(), instruction, current.scene_order),
    )
    return {
        "kind": "visual_brief",
        "before": current.model_dump(mode="json"),
        "after": result.output.model_dump(mode="json"),
    }


async def _propose_shot(session, project_id, shot_id, instruction) -> dict:
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
    result = await run_agent(
        revise_shot_agent,
        _revise_prompt("shot", dto.model_dump_json(), instruction, shot.scene_order),
    )
    return {
        "kind": "shot",
        "before": dto.model_dump(mode="json"),
        "after": result.output.model_dump(mode="json"),
    }


async def propose(session: AsyncSession, project_id: str, target: str, instruction: str) -> dict:
    """Run the revise agent but DON'T persist — return ``{kind, before, after}`` so the UI can
    show a diff and let the user accept/reject. Accepting applies the EXACT proposed ``after``
    via ``apply_proposal`` (deterministic — no second, possibly-different agent run)."""
    kind, _, ident = target.partition(":")
    if not ident:
        raise ValueError("target must be 'scene:{id}', 'visual_brief:{scene_id}' or 'shot:{id}'")
    if kind == "scene":
        return await _propose_scene(session, project_id, ident, instruction)
    if kind == "visual_brief":
        return await _propose_visual_brief(session, project_id, ident, instruction)
    if kind == "shot":
        return await _propose_shot(session, project_id, ident, instruction)
    raise ValueError(f"unknown revision target kind: {kind!r}")


# --------------------------------------------------------------------------- #
# apply an accepted proposal exactly (no re-run) — the deterministic commit path
# --------------------------------------------------------------------------- #


async def _apply_scene(session, project_id, scene_id, after: dict) -> Scene:
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise LookupError("scene not found")
    if scene.locked:
        raise ValueError("scene is locked; unlock it before revising")
    # validate through the model (a malformed `after` raises ValueError -> 422, not KeyError)
    revised = SceneDraft.model_validate({**after, "order": scene.order})
    scene.title = revised.title
    scene.summary = revised.summary
    scene.beats = [b.model_dump(mode="json") for b in revised.beats]
    scene.est_duration_sec = revised.est_duration_sec
    scene.stale = False
    scene.approved = False
    scene.approved_at = None
    session.add(scene)
    await session.execute(
        update(VisualConceptSet).where(VisualConceptSet.scene_id == scene_id).values(stale=True)
    )
    await session.execute(
        update(Shot).where(Shot.scene_id == scene_id).values(stale=True, approved=False)
    )
    await _demote_if_approved(session, project_id)
    await session.commit()
    return scene


async def _apply_visual_brief(session, project_id, scene_id, after: dict) -> VisualConceptSet:
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
    cs.visual_brief = VisualBrief.model_validate(after).model_dump(mode="json")
    cs.stale = False
    session.add(cs)
    await _regate_scene(session, project_id, scene_id)  # re-gate: art direction changed
    await session.commit()
    return cs


async def _apply_shot(session, project_id, shot_id, after: dict) -> Shot:
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise LookupError("shot not found")
    if shot.locked:
        raise ValueError("shot is locked; unlock it before revising")
    # keep structural indices ours; the rest comes from the accepted proposal
    revised = ShotDTO.model_validate({**after, "order": shot.order, "scene_order": shot.scene_order})
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
    shot.approved = False
    shot.approved_at = None
    if shot.scene_id:  # a changed shot invalidates its parent scene's sign-off too
        await session.execute(
            update(Scene).where(Scene.id == shot.scene_id).values(approved=False, approved_at=None)
        )
    session.add(shot)
    await _demote_if_approved(session, project_id)
    await session.commit()
    return shot


async def apply_proposal(session: AsyncSession, project_id: str, target: str, after: dict):
    """Write an accepted proposal's ``after`` directly — the deterministic counterpart to
    ``propose`` (what the user saw in the diff is exactly what gets committed)."""
    kind, _, ident = target.partition(":")
    if not ident:
        raise ValueError("target must be 'scene:{id}', 'visual_brief:{scene_id}' or 'shot:{id}'")
    if not isinstance(after, dict) or not after:
        raise ValueError("after must be a non-empty object")
    if kind == "scene":
        return await _apply_scene(session, project_id, ident, after)
    if kind == "visual_brief":
        return await _apply_visual_brief(session, project_id, ident, after)
    if kind == "shot":
        return await _apply_shot(session, project_id, ident, after)
    raise ValueError(f"unknown revision target kind: {kind!r}")
