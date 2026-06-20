"""Persist pipeline outputs into DB rows and read them back.

Writes use clear-then-insert ("replace") semantics scoped to a project so endpoints are
idempotent. We don't declare ORM relationships (to keep async simple), so insert order is
made explicit with flushes: parents are flushed before their children to satisfy FKs.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.act import Act
from app.models.concept import LookFrame, VisualConceptSet
from app.models.enums import ProjectStatus
from app.models.project import Brief, Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.schemas.api import ClarifyAnswer, ShotUpdate
from app.services import memory_service
from app.schemas.pipeline import (
    ActDraft,
    BriefInput,
    PipelineResult,
    ScriptDraft,
    Storyboard,
    VisualBrief,
    VisualConceptSetSpec,
)

# --------------------------------------------------------------------------- #
# clears (child -> parent order)
# --------------------------------------------------------------------------- #


async def _clear_shots(session: AsyncSession, pid: str) -> None:
    await session.execute(delete(Shot).where(Shot.project_id == pid))


async def _clear_concept_sets(session: AsyncSession, pid: str) -> None:
    await session.execute(delete(LookFrame).where(LookFrame.project_id == pid))
    await session.execute(delete(VisualConceptSet).where(VisualConceptSet.project_id == pid))


async def _clear_scenes(session: AsyncSession, pid: str) -> None:
    await session.execute(delete(Scene).where(Scene.project_id == pid))


async def _clear_acts(session: AsyncSession, pid: str) -> None:
    # null the child references first so the FK holds, then drop the acts
    await session.execute(update(Scene).where(Scene.project_id == pid).values(act_id=None))
    await session.execute(delete(Act).where(Act.project_id == pid))


async def _clear_brief(session: AsyncSession, pid: str) -> None:
    await session.execute(delete(Brief).where(Brief.project_id == pid))


async def _clear_all(session: AsyncSession, pid: str) -> None:
    await _clear_shots(session, pid)
    await _clear_concept_sets(session, pid)
    await _clear_scenes(session, pid)
    await _clear_acts(session, pid)
    await _clear_brief(session, pid)


# --------------------------------------------------------------------------- #
# inserts (parents flushed before children)
# --------------------------------------------------------------------------- #


async def _insert_brief(
    session: AsyncSession,
    pid: str,
    brief: BriefInput,
    clarifications: list[ClarifyAnswer] | None = None,
) -> None:
    session.add(
        Brief(
            project_id=pid,
            raw_prompt=brief.raw_prompt,
            parsed=brief.model_dump(mode="json"),
            clarifications=[a.model_dump(mode="json") for a in clarifications or []],
        )
    )


async def _insert_acts(session: AsyncSession, pid: str, acts: list[ActDraft]) -> list[Act]:
    rows: list[Act] = []
    for a in sorted(acts, key=lambda a: a.order):
        row = Act(
            project_id=pid,
            order=a.order,
            title=a.title,
            hook=a.hook,
            open_loop=a.open_loop,
            summary=a.summary,
        )
        session.add(row)
        rows.append(row)
    await session.flush()  # acts must exist before scenes reference act_id
    return rows


def _scene_act_ids(scenes_sorted: list, acts: list[Act] | None) -> list[str | None]:
    """Assign each scene (in order) to an act by even contiguous slices — scene i of n across
    m acts goes to act floor(i*m/n). The script is written act-by-act, so order aligns."""
    n = len(scenes_sorted)
    if not acts or n == 0:
        return [None] * n
    acts_sorted = sorted(acts, key=lambda a: a.order)
    m = len(acts_sorted)
    return [acts_sorted[min(m - 1, (i * m) // n)].id for i in range(n)]


async def _insert_scenes(
    session: AsyncSession, pid: str, script: ScriptDraft, acts: list[Act] | None = None
) -> dict[int, str]:
    mapping: dict[int, str] = {}
    scenes_sorted = sorted(script.scenes, key=lambda s: s.order)
    act_ids = _scene_act_ids(scenes_sorted, acts)
    for sc, aid in zip(scenes_sorted, act_ids, strict=False):
        row = Scene(
            project_id=pid,
            act_id=aid,
            order=sc.order,
            title=sc.title,
            summary=sc.summary,
            beats=[b.model_dump(mode="json") for b in sc.beats],
            est_duration_sec=sc.est_duration_sec,
        )
        session.add(row)
        mapping[sc.order] = row.id
    await session.flush()  # scenes must exist before concept sets / shots reference scene_id
    return mapping


async def _insert_concept_sets(
    session: AsyncSession,
    pid: str,
    concept_specs: list[VisualConceptSetSpec],
    scene_id_by_order: dict[int, str],
    visual_briefs: list[VisualBrief] | None = None,
) -> None:
    # persist each scene's art direction alongside its concept set — downstream prompt
    # composition and storyboard planning read it back from here
    brief_by_order = {vb.scene_order: vb.model_dump(mode="json") for vb in visual_briefs or []}
    frames: list[LookFrame] = []
    for spec in concept_specs:
        cs = VisualConceptSet(
            project_id=pid,
            scene_id=scene_id_by_order.get(spec.scene_order),
            scene_order=spec.scene_order,
            brief=spec.brief,
            type=spec.type.value,
            status=spec.status.value,
            visual_brief=brief_by_order.get(spec.scene_order),
        )
        session.add(cs)
        for frame in spec.candidate_look_frames:
            frames.append(
                LookFrame(
                    project_id=pid,
                    concept_set_id=cs.id,
                    prompt=frame.prompt,
                    tags=frame.tags,
                    promoted_as=frame.promoted_as.value,
                    selected=frame.selected,
                    image_asset_id=frame.image_asset_id,  # None in M1
                )
            )
    await session.flush()  # concept sets must exist before look frames reference them
    for frame in frames:
        session.add(frame)
    await session.flush()


async def _insert_shots(
    session: AsyncSession,
    pid: str,
    storyboard: Storyboard,
    scene_id_by_order: dict[int, str],
    character_id_by_name: dict[str, str] | None = None,
) -> None:
    names = character_id_by_name or {}
    for shot in storyboard.all_shots:
        # automatic cast lock: the storyboard's canonical character_name resolves to the
        # CharacterProfile created by the cast stage (or by an earlier promote)
        character_id = (
            names.get(shot.character_name.strip().lower()) if shot.character_name else None
        )
        session.add(
            Shot(
                project_id=pid,
                scene_id=scene_id_by_order.get(shot.scene_order),
                order=shot.order,
                scene_order=shot.scene_order,
                purpose=shot.purpose,
                duration_sec=shot.duration_sec,
                beat=shot.beat,
                camera_spec=shot.camera_spec.model_dump(mode="json"),
                performance_spec=shot.performance_spec.model_dump(mode="json"),
                preferred_model=shot.preferred_model.value,
                acceptance_rules=shot.acceptance_rules,
                reference_look_frame_ids=shot.reference_look_frame_ids,
                transition=shot.transition.value,
                framing=shot.framing,
                screen_direction=shot.screen_direction,
                dialogue=shot.dialogue,
                speaker=shot.speaker,
                camera_id=shot.camera_id,
                character_id=character_id,
                first_frame_desc=shot.first_frame_desc,
                last_frame_desc=shot.last_frame_desc,
                motion_desc=shot.motion_desc,
                variation_type=shot.variation_type,
            )
        )
    await session.flush()


async def _scene_id_by_order(session: AsyncSession, pid: str) -> dict[int, str]:
    rows = (await session.execute(select(Scene).where(Scene.project_id == pid))).scalars().all()
    return {s.order: s.id for s in rows}


# --------------------------------------------------------------------------- #
# per-stage replace (used by the per-stage endpoints; caller commits)
# --------------------------------------------------------------------------- #


async def replace_brief(
    session: AsyncSession,
    project_id: str,
    brief: BriefInput,
    clarifications: list[ClarifyAnswer] | None = None,
) -> None:
    await _clear_brief(session, project_id)
    await _insert_brief(session, project_id, brief, clarifications)


async def stored_cast(session: AsyncSession, project_id: str):
    """The project's CharacterProfiles as CastMember DTOs (for storyboard grounding)."""
    from app.models.memory import CharacterProfile
    from app.schemas.pipeline import CastMember

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
        CastMember(
            name=r.name,
            static_features=r.description or "appearance unspecified",
            dynamic_features="; ".join(str(w) for w in r.wardrobe_rules) or "wardrobe unspecified",
        )
        for r in rows
    ]


async def stored_clarifications(session: AsyncSession, project_id: str) -> list[ClarifyAnswer]:
    """The persisted director Q&A for a project ([] when none) — read back by every
    downstream planning stage so user-stated intent survives past the brief."""
    row = (
        (await session.execute(select(Brief).where(Brief.project_id == project_id)))
        .scalars()
        .first()
    )
    if row is None or not row.clarifications:
        return []
    return [ClarifyAnswer.model_validate(a) for a in row.clarifications]


async def replace_scenes(
    session: AsyncSession,
    project_id: str,
    script: ScriptDraft,
    acts: list[Act] | None = None,
) -> dict[int, str]:
    # regenerating the script invalidates downstream concept sets and shots
    await _clear_shots(session, project_id)
    await _clear_concept_sets(session, project_id)
    await _clear_scenes(session, project_id)
    return await _insert_scenes(session, project_id, script, acts)


async def replace_acts(
    session: AsyncSession, project_id: str, acts: list[ActDraft]
) -> list[Act]:
    """Replace the project's act outline (staged /plan/outline). Nulls scene act refs first."""
    await _clear_acts(session, project_id)
    return await _insert_acts(session, project_id, acts)


async def clear_acts(session: AsyncSession, project_id: str) -> None:
    await _clear_acts(session, project_id)


async def list_acts(session: AsyncSession, project_id: str) -> list[Act]:
    res = await session.execute(
        select(Act).where(Act.project_id == project_id).order_by(Act.order)
    )
    return list(res.scalars().all())


async def stored_acts(session: AsyncSession, project_id: str) -> list[ActDraft]:
    """The persisted act outline as ActDraft DTOs (re-injected into the script prompt)."""
    rows = await list_acts(session, project_id)
    return [
        ActDraft(
            order=r.order,
            title=r.title or f"Act {r.order + 1}",
            hook=r.hook or "—",
            open_loop=r.open_loop or "—",
            summary=r.summary or "—",
        )
        for r in rows
    ]


async def replace_concept_sets(
    session: AsyncSession,
    project_id: str,
    concept_specs: list[VisualConceptSetSpec],
    scene_id_by_order: dict[int, str],
    visual_briefs: list[VisualBrief] | None = None,
) -> None:
    await _clear_concept_sets(session, project_id)
    await _insert_concept_sets(session, project_id, concept_specs, scene_id_by_order, visual_briefs)


async def replace_shots(
    session: AsyncSession,
    project_id: str,
    storyboard: Storyboard,
    scene_id_by_order: dict[int, str],
    character_id_by_name: dict[str, str] | None = None,
) -> None:
    await _clear_shots(session, project_id)
    await _insert_shots(
        session, project_id, storyboard, scene_id_by_order, character_id_by_name
    )


async def update_shot(session: AsyncSession, shot: Shot, patch: ShotUpdate) -> Shot:
    """Apply a partial shot edit. Only fields the caller actually sent are touched;
    nested specs/enums are dumped to plain JSON values for the JSON/str columns."""
    for field, value in patch.model_dump(exclude_unset=True, mode="json").items():
        setattr(shot, field, value)
    session.add(shot)
    await session.flush()
    return shot


# --------------------------------------------------------------------------- #
# full pipeline persist (atomic replace + commit)
# --------------------------------------------------------------------------- #


async def persist_pipeline(
    session: AsyncSession,
    project: Project,
    result: PipelineResult,
    clarifications: list[ClarifyAnswer] | None = None,
) -> None:
    await _clear_all(session, project.id)
    await _insert_brief(session, project.id, result.brief, clarifications)
    act_rows = await _insert_acts(session, project.id, result.acts)
    mapping = await _insert_scenes(session, project.id, result.script, act_rows)
    await _insert_concept_sets(
        session, project.id, result.concept_specs, mapping, result.visual_briefs
    )
    await memory_service.upsert_cast(session, project.id, result.cast)
    names = await memory_service.character_id_by_name(session, project.id)
    await _insert_shots(session, project.id, result.storyboard, mapping, names)

    project.status = ProjectStatus.STORYBOARDED.value
    project.aspect_ratio = result.brief.aspect_ratio.value
    project.target_duration_sec = result.brief.target_duration_sec
    session.add(project)
    await session.commit()


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #


async def list_scenes(session: AsyncSession, project_id: str) -> list[Scene]:
    res = await session.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.order)
    )
    return list(res.scalars().all())


async def list_concept_sets(
    session: AsyncSession, project_id: str
) -> list[tuple[VisualConceptSet, list[LookFrame]]]:
    cs_rows = (
        (
            await session.execute(
                select(VisualConceptSet)
                .where(VisualConceptSet.project_id == project_id)
                .order_by(VisualConceptSet.scene_order)
            )
        )
        .scalars()
        .all()
    )
    out: list[tuple[VisualConceptSet, list[LookFrame]]] = []
    for cs in cs_rows:
        frames = (
            (await session.execute(select(LookFrame).where(LookFrame.concept_set_id == cs.id)))
            .scalars()
            .all()
        )
        out.append((cs, list(frames)))
    return out


async def list_shots(session: AsyncSession, project_id: str) -> list[Shot]:
    res = await session.execute(
        select(Shot).where(Shot.project_id == project_id).order_by(Shot.order)
    )
    return list(res.scalars().all())
