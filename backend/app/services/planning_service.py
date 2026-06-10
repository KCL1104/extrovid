"""Persist pipeline outputs into DB rows and read them back.

Writes use clear-then-insert ("replace") semantics scoped to a project so endpoints are
idempotent. We don't declare ORM relationships (to keep async simple), so insert order is
made explicit with flushes: parents are flushed before their children to satisfy FKs.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import LookFrame, VisualConceptSet
from app.models.enums import ProjectStatus
from app.models.project import Brief, Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.schemas.api import ShotUpdate
from app.schemas.pipeline import (
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


async def _clear_brief(session: AsyncSession, pid: str) -> None:
    await session.execute(delete(Brief).where(Brief.project_id == pid))


async def _clear_all(session: AsyncSession, pid: str) -> None:
    await _clear_shots(session, pid)
    await _clear_concept_sets(session, pid)
    await _clear_scenes(session, pid)
    await _clear_brief(session, pid)


# --------------------------------------------------------------------------- #
# inserts (parents flushed before children)
# --------------------------------------------------------------------------- #


async def _insert_brief(session: AsyncSession, pid: str, brief: BriefInput) -> None:
    session.add(
        Brief(project_id=pid, raw_prompt=brief.raw_prompt, parsed=brief.model_dump(mode="json"))
    )


async def _insert_scenes(session: AsyncSession, pid: str, script: ScriptDraft) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for sc in script.scenes:
        row = Scene(
            project_id=pid,
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
) -> None:
    for shot in storyboard.all_shots:
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
            )
        )
    await session.flush()


async def _scene_id_by_order(session: AsyncSession, pid: str) -> dict[int, str]:
    rows = (await session.execute(select(Scene).where(Scene.project_id == pid))).scalars().all()
    return {s.order: s.id for s in rows}


# --------------------------------------------------------------------------- #
# per-stage replace (used by the per-stage endpoints; caller commits)
# --------------------------------------------------------------------------- #


async def replace_brief(session: AsyncSession, project_id: str, brief: BriefInput) -> None:
    await _clear_brief(session, project_id)
    await _insert_brief(session, project_id, brief)


async def replace_scenes(
    session: AsyncSession, project_id: str, script: ScriptDraft
) -> dict[int, str]:
    # regenerating the script invalidates downstream concept sets and shots
    await _clear_shots(session, project_id)
    await _clear_concept_sets(session, project_id)
    await _clear_scenes(session, project_id)
    return await _insert_scenes(session, project_id, script)


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
) -> None:
    await _clear_shots(session, project_id)
    await _insert_shots(session, project_id, storyboard, scene_id_by_order)


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


async def persist_pipeline(session: AsyncSession, project: Project, result: PipelineResult) -> None:
    await _clear_all(session, project.id)
    await _insert_brief(session, project.id, result.brief)
    mapping = await _insert_scenes(session, project.id, result.script)
    await _insert_concept_sets(
        session, project.id, result.concept_specs, mapping, result.visual_briefs
    )
    await _insert_shots(session, project.id, result.storyboard, mapping)

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
