"""Linear async planning pipeline: Brief -> Script -> Visual plans -> Storyboard.

Per-stage functions are exposed so the API can run a single stage; ``run_pipeline`` chains
them. This is intentionally a plain async chain — branching/routing (pydantic-graph) is a
later-phase concern.

Prompt builders embed machine-readable markers (TARGET_DURATION_SEC, SCENE_ORDER) so the
mock model stays consistent with the brief; real Qwen also benefits from the explicit cues.
"""

import asyncio
from collections.abc import Awaitable, Callable

from app.agents.brief_agent import brief_agent
from app.agents.cast_agent import cast_agent
from app.agents.clarify_agent import clarify_agent
from app.agents.outline_agent import outline_agent
from app.agents.script_agent import script_agent
from app.agents.script_review_agent import ScriptCoherence, review_script_coherence
from app.agents.storyboard_agent import scene_storyboard_agent
from app.agents.tiers import (
    Tier,
    format_block,
    scene_shot_tier_block,
    script_tier_block,
    tier_for,
)
from app.agents.visual_dev_agent import visual_dev_agent
from app.core.agent_run import run_agent
from app.core.config import get_settings
from app.models.enums import (
    MAX_SCENE_DURATION_SEC,
    MAX_TARGET_DURATION_SEC,
    MIN_TARGET_DURATION_SEC,
    VideoFormat,
)
from app.schemas.api import ClarifyAnswer, ClarifyResult
from app.schemas.pipeline import (
    ActDraft,
    BriefInput,
    CastMember,
    PipelineResult,
    SceneDraft,
    SceneVisualPlan,
    ScriptDraft,
    ShotDTO,
    Storyboard,
    StoryboardScene,
    VisualConceptSetSpec,
)

# --------------------------------------------------------------------------- #
# prompt builders
# --------------------------------------------------------------------------- #


def creative_direction_block(clarifications: list[ClarifyAnswer] | None) -> str:
    """Render the director Q&A answers as a prompt block ("" when nothing was answered).

    User-stated intent must be re-injected into EVERY planning stage, not consumed once
    by the brief and discarded — otherwise "anime style, melancholy ending" can silently
    evaporate by the storyboard stage (docs/vimax-research.md A6).
    """
    answered = [a for a in clarifications or [] if a.answer and a.answer.strip()]
    if not answered:
        return ""
    lines = "".join(f"- {a.question} -> {a.answer.strip()}\n" for a in answered)
    return "\nCreative direction (director Q&A — honor these in every choice):\n" + lines


def fold_clarifications(raw_prompt: str, clarifications: list[ClarifyAnswer] | None) -> str:
    """Deterministically fold director Q&A answers into the prompt fed to the BriefAgent.

    Skipped/empty answers are omitted; with no usable answers the prompt is untouched.
    """
    block = creative_direction_block(clarifications)
    return raw_prompt + "\n" + block if block else raw_prompt


def act_block(acts: list[ActDraft] | None) -> str:
    """Render the LONG-tier chapter outline as a prompt block so the script realizes the
    pre-approved structure act by act ("" when there is no outline)."""
    if not acts:
        return ""
    lines = "".join(
        f"- Act {a.order + 1} — {a.title}: {a.summary} (hook: {a.hook}; open loop: {a.open_loop})\n"
        for a in sorted(acts, key=lambda a: a.order)
    )
    return (
        "\nACT STRUCTURE (write the scenes to realize these acts IN ORDER — each act becomes a "
        "contiguous run of scenes; honor each act's hook and open loop):\n" + lines
    )


def build_script_prompt(
    brief: BriefInput,
    clarifications: list[ClarifyAnswer] | None = None,
    acts: list[ActDraft] | None = None,
) -> str:
    return (
        "Write a script for this brief.\n"
        f"Raw request: {brief.raw_prompt}\n"
        f"Product: {brief.product}\n"
        f"Story: {brief.story}\n"
        f"Platform: {brief.platform}\n"
        f"Style: {brief.style}\n"
        f"Audience: {brief.audience}\n"
        f"Target duration: {brief.target_duration_sec}s\n"
        + script_tier_block(tier_for(brief.target_duration_sec), brief.target_duration_sec)
        + format_block(brief.format.value if brief.format else None)
        + act_block(acts)
        + creative_direction_block(clarifications)
    )


def build_outline_prompt(
    brief: BriefInput, clarifications: list[ClarifyAnswer] | None = None
) -> str:
    return (
        "Design the act/chapter outline for this long-form brief.\n"
        f"Raw request: {brief.raw_prompt}\n"
        f"Story: {brief.story}\n"
        f"Platform: {brief.platform}\n"
        f"Audience: {brief.audience}\n"
        f"Target duration: {brief.target_duration_sec}s\n"
        + creative_direction_block(clarifications)
    )


def build_visual_prompt(
    scene: SceneDraft, clarifications: list[ClarifyAnswer] | None = None
) -> str:
    beats = "; ".join(b.description for b in scene.beats)
    return (
        f"Develop the visual look for this scene. SCENE_ORDER={scene.order}\n"
        f"Title: {scene.title}\n"
        f"Summary: {scene.summary}\n"
        f"Beats: {beats}\n"
        "Use SCENE_ORDER for both the visual_brief.scene_order and concept_set.scene_order."
        + creative_direction_block(clarifications)
    )


def build_cast_prompt(script: ScriptDraft) -> str:
    scene_lines = []
    for s in script.scenes:
        beats = "; ".join(
            " ".join(filter(None, [b.description, b.narration, b.dialogue])) for b in s.beats
        )
        scene_lines.append(f"- scene {s.order} ({s.title}): {s.summary}. Beats: {beats}")
    return (
        "Extract the cast from this script.\n"
        f"Logline: {script.logline}\n"
        "Scenes:\n" + "\n".join(scene_lines)
    )


def cast_block(cast: list[CastMember] | None) -> str:
    if not cast:
        return ""
    lines = "".join(
        f"- {c.name}: {c.static_features}; wearing {c.dynamic_features}\n" for c in cast
    )
    return (
        "\nCAST (set character_name to the EXACT name when a shot features one; describe "
        "them by these visible features, never by bare name):\n" + lines
    )


def build_continuity_bible(scenes: list[SceneDraft]) -> str:
    """A compact whole-arc context injected into EVERY per-scene planner (P2).

    The per-scene fold otherwise sees only its own scene plus the adjacent ``_scene_tail``
    baton, so locations/props/time-of-day drift across non-adjacent scenes. The cast (with
    appearance) is the character half of the bible (``cast_block``); this is the world/arc
    half — the cheapest, highest-leverage long-form drift defense (ViMax/VideoStudio)."""
    if not scenes:
        return ""
    arc = "\n".join(
        f"- S{s.order + 1} {s.title}: {s.summary}" for s in sorted(scenes, key=lambda s: s.order)
    )
    return (
        "\nSTORY CONTINUITY (the whole arc — keep locations, props, wardrobe, palette and "
        "time-of-day consistent with these scenes; never contradict an earlier scene unless "
        "the script motivates it):\n" + arc
    )


def build_scene_storyboard_prompt(
    scene: SceneDraft,
    visual_brief,
    budget_sec: float,
    clarifications: list[ClarifyAnswer] | None = None,
    cast: list[CastMember] | None = None,
    prev_tail: str | None = None,
    tier: Tier | None = None,
    bible: str | None = None,
) -> str:
    beats = "; ".join(
        " ".join(filter(None, [b.description, b.narration, b.dialogue])) for b in scene.beats
    )
    direction = ""
    if visual_brief is not None:
        bits = [
            getattr(visual_brief, "visual_style", None),
            getattr(visual_brief, "mood", None),
            getattr(visual_brief, "camera_language", None),
            getattr(visual_brief, "lighting", None),
        ]
        joined = ", ".join(b for b in bits if b)
        if joined:
            direction = f"\nVisual direction (honor it in camera_spec choices): {joined}"
    # axis lock (180-degree line): set per-shot screen_direction consistently across the scene
    if visual_brief is not None and getattr(visual_brief, "axis_lock", False):
        direction += (
            "\nHold the 180-degree line: give each shot a screen_direction and keep it "
            "consistent across the scene so the spatial geometry never flips across a cut."
        )
    # the continuity baton: each scene is planned in isolation, so the previous scene's
    # ending is the ONLY cross-scene memory the planner gets — it is what makes a seam
    # match-cut (or a motivated hard cut) authorable instead of accidental.
    continuity = ""
    if prev_tail:
        continuity = (
            f"\nCONTINUITY — the previous scene {prev_tail}. Preserve screen direction, "
            "wardrobe, palette and lighting across the cut unless the script motivates a "
            "change; if this scene opens on the same space, plan the first shot's "
            "first_frame_desc to graphically match that ending."
        )
    return (
        "Plan the shot list for this ONE scene.\n"
        f"SCENE_ORDER={scene.order}\n"
        f"TARGET_DURATION_SEC={budget_sec:g}\n"
        f"Title: {scene.title}\n"
        f"Summary: {scene.summary}\n"
        f"Beats: {beats}"
        + direction
        + continuity
        + (scene_shot_tier_block(tier, budget_sec, scene.order) if tier else "")
        + (bible or "")
        + cast_block(cast)
        + creative_direction_block(clarifications)
    )


def build_storyboard_prompt(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
    clarifications: list[ClarifyAnswer] | None = None,
    cast: list[CastMember] | None = None,
) -> str:
    # the storyboard must see the look-dev direction, not just the script — camera
    # language and mood per scene should shape shot sizes, movement, and pacing
    direction_by_order: dict[int, str] = {}
    for vb in visual_briefs:
        bits = [
            getattr(vb, "visual_style", None),
            getattr(vb, "mood", None),
            getattr(vb, "camera_language", None),
            getattr(vb, "lighting", None),
        ]
        direction_by_order[vb.scene_order] = ", ".join(b for b in bits if b)
    scene_lines = "\n".join(
        f"- scene {s.order} ({s.title}): {s.summary}"
        + (
            f"\n  visual direction: {direction_by_order[s.order]}"
            if direction_by_order.get(s.order)
            else ""
        )
        for s in script.scenes
    )
    return (
        "Turn this script into an executable shot list.\n"
        f"TARGET_DURATION_SEC={target_duration_sec}\n"
        f"Logline: {script.logline}\n"
        f"Scenes:\n{scene_lines}\n"
        f"Concept sets available: {len(concept_specs)}\n"
        "Honor each scene's visual direction in camera_spec choices. "
        "Produce 5-10 shots total, globally ordered from 0, durations summing near the target."
        + cast_block(cast)
        + creative_direction_block(clarifications)
    )


# --------------------------------------------------------------------------- #
# per-stage runners
# --------------------------------------------------------------------------- #


async def run_clarify(raw_prompt: str) -> ClarifyResult:
    """Stateless plan-stage triage: should we ask the user clarifying questions first?"""
    result = await run_agent(clarify_agent, raw_prompt)
    return result.output


async def run_brief(
    raw_prompt: str,
    clarifications: list[ClarifyAnswer] | None = None,
    target_duration_sec: int | None = None,
    format: VideoFormat | None = None,
) -> BriefInput:
    result = await run_agent(brief_agent, fold_clarifications(raw_prompt, clarifications))
    brief = result.output
    # an explicit length/format selection is AUTHORITATIVE over the agent's text inference
    if target_duration_sec is not None:
        brief.target_duration_sec = max(
            MIN_TARGET_DURATION_SEC, min(MAX_TARGET_DURATION_SEC, target_duration_sec)
        )
    if format is not None:
        brief.format = format
    return brief


async def run_outline(
    brief: BriefInput, clarifications: list[ClarifyAnswer] | None = None
) -> list[ActDraft]:
    """LONG-tier only: the chapter structure above scenes, generated before the script."""
    result = await run_agent(outline_agent, build_outline_prompt(brief, clarifications))
    return result.output.acts


async def run_script(
    brief: BriefInput,
    clarifications: list[ClarifyAnswer] | None = None,
    acts: list[ActDraft] | None = None,
) -> ScriptDraft:
    result = await run_agent(
        script_agent, build_script_prompt(brief, clarifications, acts), deps=brief
    )
    return result.output


def _pick_best_index(verdicts: list[ScriptCoherence | None]) -> int:
    """Index of the highest-coherence draft; unjudged (None) drafts sort last."""
    return max(
        range(len(verdicts)),
        key=lambda i: verdicts[i].coherence if verdicts[i] else -1.0,
    )


async def _best_script(
    brief: BriefInput,
    clarifications: list[ClarifyAnswer] | None,
    acts: list[ActDraft] | None,
    emit: Callable[[dict], Awaitable[None]],
) -> ScriptDraft:
    """Best-of-N: draft the script N times concurrently and keep the one the coherence judge
    scores highest — script quality swings draw-to-draw, and picking the max of N cuts the
    bad-draw tail. Mock / N<=1 short-circuits to a single draft (no judging), so offline tests
    and the one-prompt-to-video mock path are unchanged."""
    n = max(1, get_settings().script_best_of)
    if get_settings().use_mock_llm or n == 1:
        return await run_script(brief, clarifications, acts)
    drafts = await asyncio.gather(*(run_script(brief, clarifications, acts) for _ in range(n)))
    await emit(
        {"phase": "script", "status": "progress", "text": f"Evaluating {n} script drafts…"}
    )
    verdicts = await asyncio.gather(*(review_script_coherence(d) for d in drafts))
    best = _pick_best_index(verdicts)
    if verdicts[best]:
        await emit(
            {
                "phase": "script",
                "status": "progress",
                "text": f"Kept the strongest draft (coherence {verdicts[best].coherence:.0f}/10)",
            }
        )
    return drafts[best]


async def run_cast(script: ScriptDraft) -> list[CastMember]:
    result = await run_agent(cast_agent, build_cast_prompt(script))
    return result.output.characters


async def run_visual_plan(
    scene: SceneDraft, clarifications: list[ClarifyAnswer] | None = None
) -> SceneVisualPlan:
    result = await run_agent(
        visual_dev_agent, build_visual_prompt(scene, clarifications), deps=scene
    )
    return result.output


def _scene_tail(shots: list[ShotDTO]) -> str | None:
    """The continuity baton handed to the next scene's planner: the closing image, framing,
    and subject of this scene's last shot (built in Python from already-planned shots)."""
    if not shots:
        return None
    last = shots[-1]  # last by global order
    bits: list[str] = []
    if last.last_frame_desc:
        bits.append(f"ended on: {last.last_frame_desc}")
    elif last.first_frame_desc:
        bits.append(f"ended near: {last.first_frame_desc}")
    if last.framing:
        bits.append(f"final framing: {last.framing}")
    if last.screen_direction:
        bits.append(f"screen direction: {last.screen_direction}")
    subject = last.performance_spec.subject if last.performance_spec else ""
    if subject:
        bits.append(f"subject last in frame: {subject}")
    return "; ".join(bits) or None


def _anchor_subject(shot: ShotDTO, cast_by_name: dict[str, CastMember]) -> str | None:
    """Repair a cast shot whose `subject` names the character with a BARE name. The planner
    is told to anchor by appearance, but ~⅓ of shots still emit "Elena" instead of "Elena
    (cropped hair, grey flight suit)" — and a bare name gives the video model no identity to
    hold, which is the main source of cross-shot drift. Folds in the cast member's static
    features as a deterministic safety net. Returns the repaired subject, or None to leave it."""
    if not shot.character_name:
        return None
    member = cast_by_name.get(shot.character_name.strip().lower())
    if member is None:
        return None
    subject = (shot.performance_spec.subject or "").strip()
    if "(" in subject or "," in subject:
        return None  # already appearance-anchored
    feats = member.static_features.strip().rstrip(".")
    return f"{subject} ({feats})" if subject else f"{member.name} ({feats})"


async def run_storyboard(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
    clarifications: list[ClarifyAnswer] | None = None,
    cast: list[CastMember] | None = None,
    on_scene: Callable[[int, int, str], Awaitable[None]] | None = None,
) -> Storyboard:
    """Per-scene fold: each scene is planned by its own agent call against its own duration
    budget, threading a CONTINUITY baton from the previous scene's ending. Global shot order
    AND camera_id are renumbered in Python afterwards (structural indices are never the LLM's
    job) — so camera_id no longer resets to 0 each scene. This breaks the 5-10-shot ceiling
    while keeping cross-scene continuity authorable (the cost is per-scene-serial planning)."""
    briefs_by_order = {vb.scene_order: vb for vb in visual_briefs}
    total_est = sum(s.est_duration_sec for s in script.scenes) or 1.0
    scale = target_duration_sec / total_est
    tier = tier_for(target_duration_sec)  # pacing/ASL guidance scales with overall length
    bible = build_continuity_bible(script.scenes)  # whole-arc context for every scene planner
    cast_by_name = {c.name.strip().lower(): c for c in (cast or [])}

    scenes_out: list[StoryboardScene] = []
    next_order = 0
    camera_offset = 0  # makes per-scene-local camera_ids globally unique
    prev_tail: str | None = None
    scenes_sorted = sorted(script.scenes, key=lambda s: s.order)
    for i, scene in enumerate(scenes_sorted):
        # progress hook: announce each scene before its (multi-second) planning call so the
        # SSE stream can show "breaking down scene k of n" — this is also what keeps the
        # connection from idling through the longest planning stage.
        if on_scene:
            await on_scene(i, len(scenes_sorted), scene.title)
        budget = min(MAX_SCENE_DURATION_SEC, round(scene.est_duration_sec * scale, 1))
        result = await run_agent(
            scene_storyboard_agent,
            build_scene_storyboard_prompt(
                scene,
                briefs_by_order.get(scene.order),
                budget,
                clarifications,
                cast,
                prev_tail,
                tier,
                bible,
            ),
            deps=budget,
        )
        shots: list[ShotDTO] = []
        max_local_cam = 0
        for shot in sorted(result.output.shots, key=lambda s: s.order):
            local_cam = shot.camera_id or 0
            max_local_cam = max(max_local_cam, local_cam)
            update = {
                "order": next_order,
                "scene_order": scene.order,
                "camera_id": camera_offset + local_cam,
            }
            anchored = _anchor_subject(shot, cast_by_name)
            if anchored is not None:
                update["performance_spec"] = shot.performance_spec.model_copy(
                    update={"subject": anchored}
                )
            shots.append(shot.model_copy(update=update))
            next_order += 1
        camera_offset += max_local_cam + 1  # next scene's cameras start past this one's
        scenes_out.append(StoryboardScene(scene_order=scene.order, shots=shots))
        prev_tail = _scene_tail(shots)
    return Storyboard(scenes=scenes_out)


# --------------------------------------------------------------------------- #
# full pipeline
# --------------------------------------------------------------------------- #


async def run_pipeline(
    brief_in: BriefInput,
    clarifications: list[ClarifyAnswer] | None = None,
    target_duration_sec: int | None = None,
    format: VideoFormat | None = None,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> PipelineResult:
    """Run the whole plan. ``on_progress`` (optional) is awaited with a stage dict at every
    milestone — ``{phase, status: running|progress|done, detail?/text?/index?/total?}`` — so a
    streaming endpoint can show live per-stage progress. Without it the run is silent (the
    ``/run`` callers are unaffected)."""

    async def emit(event: dict) -> None:
        if on_progress:
            await on_progress(event)

    await emit({"phase": "brief", "status": "running"})
    filled = await run_brief(brief_in.raw_prompt, clarifications, target_duration_sec, format)
    await emit(
        {
            "phase": "brief",
            "status": "done",
            "detail": f"{filled.target_duration_sec}s · "
            f"{tier_for(filled.target_duration_sec).name.lower()} · {filled.aspect_ratio.value}",
        }
    )

    # LONG tier: design the chapter outline first, then write the script to realize it
    acts: list[ActDraft] = []
    await emit({"phase": "script", "status": "running"})
    if tier_for(filled.target_duration_sec) is Tier.LONG:
        await emit({"phase": "script", "status": "progress", "text": "Designing the chapter outline…"})
        acts = await run_outline(filled, clarifications)
    script = await _best_script(filled, clarifications, acts, emit)
    await emit(
        {"phase": "script", "status": "done", "detail": f'{len(script.scenes)} scenes — "{script.logline}"'}
    )

    # cast extraction and per-scene visual dev are independent — run concurrently
    n = len(script.scenes)
    await emit({"phase": "looks", "status": "running", "total": n})
    looks_done = 0

    async def _plan(scene: SceneDraft) -> SceneVisualPlan:
        nonlocal looks_done
        plan = await run_visual_plan(scene, clarifications)
        looks_done += 1
        await emit(
            {"phase": "looks", "status": "progress", "index": looks_done, "total": n,
             "text": f"Developing looks — {looks_done} of {n} scenes"}
        )
        return plan

    cast, *plans = await asyncio.gather(run_cast(script), *(_plan(scene) for scene in script.scenes))
    visual_briefs = [plan.visual_brief for plan in plans]
    concept_specs = [plan.concept_set for plan in plans]
    await emit({"phase": "looks", "status": "done", "detail": f"{len(concept_specs)} concept sets planned"})

    await emit({"phase": "board", "status": "running", "total": n})

    async def _board(index: int, total: int, title: str) -> None:
        # ``index`` is the count *completed* before this scene starts, so the bar reflects done
        # work — it no longer hits 100% the moment the last (multi-second) scene merely starts.
        await emit(
            {"phase": "board", "status": "progress", "index": index, "total": total,
             "text": f"Breaking down scene {index + 1} of {total}: {title}"}
        )

    storyboard = await run_storyboard(
        script, visual_briefs, concept_specs, filled.target_duration_sec, clarifications, cast,
        on_scene=_board,
    )
    await emit({"phase": "board", "status": "done", "detail": "shot list ready"})
    return PipelineResult(
        brief=filled,
        acts=acts,
        script=script,
        cast=cast,
        visual_briefs=visual_briefs,
        concept_specs=concept_specs,
        storyboard=storyboard,
    )
