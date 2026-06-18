"""Linear async planning pipeline: Brief -> Script -> Visual plans -> Storyboard.

Per-stage functions are exposed so the API can run a single stage; ``run_pipeline`` chains
them. This is intentionally a plain async chain — branching/routing (pydantic-graph) is a
later-phase concern.

Prompt builders embed machine-readable markers (TARGET_DURATION_SEC, SCENE_ORDER) so the
mock model stays consistent with the brief; real Qwen also benefits from the explicit cues.
"""

import asyncio

from app.agents.brief_agent import brief_agent
from app.agents.cast_agent import cast_agent
from app.agents.clarify_agent import clarify_agent
from app.agents.script_agent import script_agent
from app.agents.storyboard_agent import scene_storyboard_agent
from app.agents.visual_dev_agent import visual_dev_agent
from app.models.enums import MAX_SCENE_DURATION_SEC
from app.schemas.api import ClarifyAnswer, ClarifyResult
from app.schemas.pipeline import (
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


def build_script_prompt(
    brief: BriefInput, clarifications: list[ClarifyAnswer] | None = None
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


def build_scene_storyboard_prompt(
    scene: SceneDraft,
    visual_brief,
    budget_sec: float,
    clarifications: list[ClarifyAnswer] | None = None,
    cast: list[CastMember] | None = None,
    prev_tail: str | None = None,
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
    result = await clarify_agent.run(raw_prompt)
    return result.output


async def run_brief(
    raw_prompt: str, clarifications: list[ClarifyAnswer] | None = None
) -> BriefInput:
    result = await brief_agent.run(fold_clarifications(raw_prompt, clarifications))
    return result.output


async def run_script(
    brief: BriefInput, clarifications: list[ClarifyAnswer] | None = None
) -> ScriptDraft:
    result = await script_agent.run(build_script_prompt(brief, clarifications), deps=brief)
    return result.output


async def run_cast(script: ScriptDraft) -> list[CastMember]:
    result = await cast_agent.run(build_cast_prompt(script))
    return result.output.characters


async def run_visual_plan(
    scene: SceneDraft, clarifications: list[ClarifyAnswer] | None = None
) -> SceneVisualPlan:
    result = await visual_dev_agent.run(build_visual_prompt(scene, clarifications), deps=scene)
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


async def run_storyboard(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
    clarifications: list[ClarifyAnswer] | None = None,
    cast: list[CastMember] | None = None,
) -> Storyboard:
    """Per-scene fold: each scene is planned by its own agent call against its own duration
    budget, threading a CONTINUITY baton from the previous scene's ending. Global shot order
    AND camera_id are renumbered in Python afterwards (structural indices are never the LLM's
    job) — so camera_id no longer resets to 0 each scene. This breaks the 5-10-shot ceiling
    while keeping cross-scene continuity authorable (the cost is per-scene-serial planning)."""
    briefs_by_order = {vb.scene_order: vb for vb in visual_briefs}
    total_est = sum(s.est_duration_sec for s in script.scenes) or 1.0
    scale = target_duration_sec / total_est

    scenes_out: list[StoryboardScene] = []
    next_order = 0
    camera_offset = 0  # makes per-scene-local camera_ids globally unique
    prev_tail: str | None = None
    for scene in sorted(script.scenes, key=lambda s: s.order):
        budget = min(MAX_SCENE_DURATION_SEC, round(scene.est_duration_sec * scale, 1))
        result = await scene_storyboard_agent.run(
            build_scene_storyboard_prompt(
                scene, briefs_by_order.get(scene.order), budget, clarifications, cast, prev_tail
            ),
            deps=budget,
        )
        shots: list[ShotDTO] = []
        max_local_cam = 0
        for shot in sorted(result.output.shots, key=lambda s: s.order):
            local_cam = shot.camera_id or 0
            max_local_cam = max(max_local_cam, local_cam)
            shots.append(
                shot.model_copy(
                    update={
                        "order": next_order,
                        "scene_order": scene.order,
                        "camera_id": camera_offset + local_cam,
                    }
                )
            )
            next_order += 1
        camera_offset += max_local_cam + 1  # next scene's cameras start past this one's
        scenes_out.append(StoryboardScene(scene_order=scene.order, shots=shots))
        prev_tail = _scene_tail(shots)
    return Storyboard(scenes=scenes_out)


# --------------------------------------------------------------------------- #
# full pipeline
# --------------------------------------------------------------------------- #


async def run_pipeline(
    brief_in: BriefInput, clarifications: list[ClarifyAnswer] | None = None
) -> PipelineResult:
    filled = await run_brief(brief_in.raw_prompt, clarifications)
    script = await run_script(filled, clarifications)

    # cast extraction and per-scene visual dev are independent — run concurrently
    cast, *plans = await asyncio.gather(
        run_cast(script),
        *(run_visual_plan(scene, clarifications) for scene in script.scenes),
    )
    visual_briefs = [plan.visual_brief for plan in plans]
    concept_specs = [plan.concept_set for plan in plans]

    storyboard = await run_storyboard(
        script, visual_briefs, concept_specs, filled.target_duration_sec, clarifications, cast
    )
    return PipelineResult(
        brief=filled,
        script=script,
        cast=cast,
        visual_briefs=visual_briefs,
        concept_specs=concept_specs,
        storyboard=storyboard,
    )
