"""AI review of finished takes — the spec's ReviewAgent loop, wired into ingest.

After a ShotVersion's video lands, the ReviewAgent judges it against the shot's
acceptance rules and the scene's visual direction, then writes ``score`` / ``review`` /
``status`` onto the version. With ``review_vision`` enabled (and a real LLM), the take's
poster frame is attached so the model reviews what was actually rendered, not just the
prompt. Review is best-effort: a failure never blocks ingestion.
"""

from pydantic_ai import ImageUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.review_agent import keyframe_review_agent, review_agent
from app.core.config import get_settings
from app.core.logging import log
from app.models.concept import LookFrame, VisualConceptSet
from app.models.enums import ShotVersionStatus
from app.models.generation import ShotVersion
from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.services.asset_service import asset_url
from app.services.prompt_service import portrait_view_for


async def previous_shot_take(
    session: AsyncSession, project_id: str, shot: Shot
) -> tuple[Shot, ShotVersion] | None:
    """The selected (else latest finished) take of the shot right before this one.

    Shared by continuation seeding (generate_service) and continuity review.
    """
    prev = (
        (
            await session.execute(
                select(Shot)
                .where(Shot.project_id == project_id, Shot.order < shot.order)
                .order_by(Shot.order.desc())
            )
        )
        .scalars()
        .first()
    )
    if prev is None:
        return None
    versions = (
        (
            await session.execute(
                select(ShotVersion).where(
                    ShotVersion.shot_id == prev.id, ShotVersion.output_asset_id.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    if not versions:
        return None
    return prev, next((v for v in versions if v.selected), versions[-1])


async def _scene_visual_brief(session: AsyncSession, shot: Shot) -> dict | None:
    if not shot.scene_id:
        return None
    cs = (
        (
            await session.execute(
                select(VisualConceptSet).where(VisualConceptSet.scene_id == shot.scene_id)
            )
        )
        .scalars()
        .first()
    )
    return cs.visual_brief if cs else None


def _build_review_prompt(shot: Shot, version: ShotVersion, visual_brief: dict | None) -> str:
    cam = shot.camera_spec or {}
    perf = shot.performance_spec or {}
    vb = visual_brief or {}
    lines = [
        f"Shot #{shot.order} — {shot.purpose}",
        f"Camera: {cam.get('shot_size', '?')} {cam.get('angle', '')} {cam.get('movement', '')}",
        f"Performance: {perf.get('subject', '?')} — {perf.get('action', '')}"
        + (f" ({perf['emotion']})" if perf.get("emotion") else ""),
        *([f"Framing: {shot.framing}"] if shot.framing else []),
        *(
            [f"Planned end state: {shot.last_frame_desc}"]
            if shot.last_frame_desc
            else []
        ),
        f"Beat: {shot.beat}",
        f"Target duration: {shot.duration_sec}s"
        + (f" | actual: {version.duration_sec:.1f}s" if version.duration_sec else ""),
        f"Model used: {version.model or 'unknown'}",
        f"Generation prompt: {version.prompt or ''}",
    ]
    if vb:
        lines.append(
            "Visual direction: "
            + "; ".join(
                str(vb.get(k))
                for k in ("visual_style", "mood", "lighting", "camera_language")
                if vb.get(k)
            )
        )
        if vb.get("negative_rules"):
            lines.append("Forbidden: " + "; ".join(str(r) for r in vb["negative_rules"]))
    lines.append("Acceptance rules:")
    lines.extend(f"- {rule}" for rule in (shot.acceptance_rules or ["subject clearly in frame"]))
    return "\n".join(lines)


async def review_version(session: AsyncSession, version: ShotVersion) -> ShotVersion:
    """Run the AI review and persist the verdict onto the version. Caller owns commit."""
    settings = get_settings()
    shot = await session.get(Shot, version.shot_id)
    if shot is None:
        return version
    visual_brief = await _scene_visual_brief(session, shot)
    prompt = _build_review_prompt(shot, version, visual_brief)

    user_input: str | list = prompt
    if settings.review_vision and not settings.use_mock_llm and version.thumbnail_asset_id:
        thumb_url = await asset_url(session, version.thumbnail_asset_id)
        if thumb_url and thumb_url.startswith("http"):
            images = [ImageUrl(url=thumb_url)]
            # continuity: judge against the most recent real pixels of the timeline,
            # not just text — wardrobe drift / palette jumps / identity flips show here
            found = await previous_shot_take(session, shot.project_id, shot)
            if found:
                prev_shot, prev_version = found
                if prev_version.thumbnail_asset_id:
                    prev_url = await asset_url(session, prev_version.thumbnail_asset_id)
                    if prev_url and prev_url.startswith("http"):
                        prompt += (
                            "\nImage 1 is the take under review (poster frame). "
                            f"Image 2 is a frame from the PREVIOUS shot (#{prev_shot.order}) — "
                            "check continuity against it."
                        )
                        images.append(ImageUrl(url=prev_url))
            user_input = [prompt, *images]

    result = (await review_agent.run(user_input)).output
    version.score = result.score
    version.review = result.model_dump(mode="json")
    version.status = (
        ShotVersionStatus.ACCEPTED.value if result.verdict == "pass" else version.status
    )
    session.add(version)
    return version


async def review_version_safe(session: AsyncSession, version: ShotVersion) -> None:
    """Best-effort review + commit; never raises (ingest must not fail on review)."""
    try:
        await review_version(session, version)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - review is advisory, never fatal
        log.warning("review.failed version=%s err=%s", version.id, exc)
        await session.rollback()


_VIEW_PHRASE = {
    "back": "(seen from behind — the face must NOT be visible)",
    "side": "(profile)",
    "front": "(facing camera)",
}


def _build_keyframe_review_prompt(
    shot: Shot, frame: LookFrame, character: CharacterProfile | None
) -> str:
    perf = shot.performance_spec or {}
    view = portrait_view_for(shot)
    lines = [
        f"Shot #{shot.order} — {shot.purpose}",
        *([f"Planned opening frame: {shot.first_frame_desc}"] if shot.first_frame_desc else []),
        *([f"Blocking/framing: {shot.framing}"] if shot.framing else []),
        f"Subject: {perf.get('subject', '?')}",
        f"Expected camera view of the subject: {view} {_VIEW_PHRASE[view]}",
        *([f"Director's notes: {shot.extra_direction}"] if shot.extra_direction else []),
        f"Keyframe prompt: {frame.prompt}",
    ]
    if character:
        appearance = (character.description or "").strip()
        if appearance:
            lines.append(f"Character {character.name} canonical appearance: {appearance}")
        if character.wardrobe_rules:
            lines.append("Wardrobe: " + ", ".join(str(r) for r in character.wardrobe_rules[:3]))
    return "\n".join(lines)


async def review_keyframe(
    session: AsyncSession,
    frame: LookFrame,
    shot: Shot,
    character: CharacterProfile | None = None,
) -> LookFrame:
    """Run the keyframe gate and persist the verdict on the LookFrame. Caller owns commit.

    Judges the still keyframe (identity/composition/view) BEFORE video budget is spent. With
    vision enabled (real LLM), the keyframe image and the view-matched reference portrait are
    attached so identity is checked against ground truth, not just text.
    """
    settings = get_settings()
    prompt = _build_keyframe_review_prompt(shot, frame, character)

    user_input: str | list = prompt
    if settings.review_vision and not settings.use_mock_llm and frame.image_asset_id:
        kf_url = await asset_url(session, frame.image_asset_id)
        if kf_url and kf_url.startswith("http"):
            images = [ImageUrl(url=kf_url)]
            if character:
                portraits = character.portrait_assets or {}
                view = portrait_view_for(shot)
                portrait_id = portraits.get(view) or portraits.get("front")
                if portrait_id:
                    p_url = await asset_url(session, portrait_id)
                    if p_url and p_url.startswith("http"):
                        prompt += (
                            "\nImage 1 is the keyframe under review. Image 2 is the "
                            f"character's reference portrait ({view} view) — the identity "
                            "ground truth; check the keyframe matches it."
                        )
                        images.append(ImageUrl(url=p_url))
            user_input = [prompt, *images]

    result = (await keyframe_review_agent.run(user_input)).output
    frame.score = result.score
    frame.review = result.model_dump(mode="json")
    session.add(frame)
    return frame


async def review_keyframe_safe(
    session: AsyncSession,
    frame: LookFrame,
    shot: Shot,
    character: CharacterProfile | None = None,
) -> None:
    """Best-effort keyframe review + commit; never raises (the gate is advisory)."""
    try:
        await review_keyframe(session, frame, shot, character)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - the gate is advisory, never fatal
        log.warning("keyframe_review.failed frame=%s err=%s", frame.id, exc)
        await session.rollback()
