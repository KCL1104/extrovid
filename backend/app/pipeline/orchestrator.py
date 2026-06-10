"""Linear async planning pipeline: Brief -> Script -> Visual plans -> Storyboard.

Per-stage functions are exposed so the API can run a single stage; ``run_pipeline`` chains
them. This is intentionally a plain async chain — branching/routing (pydantic-graph) is a
later-phase concern.

Prompt builders embed machine-readable markers (TARGET_DURATION_SEC, SCENE_ORDER) so the
mock model stays consistent with the brief; real Qwen also benefits from the explicit cues.
"""

import asyncio

from app.agents.brief_agent import brief_agent
from app.agents.clarify_agent import clarify_agent
from app.agents.script_agent import script_agent
from app.agents.storyboard_agent import storyboard_agent
from app.agents.visual_dev_agent import visual_dev_agent
from app.schemas.api import ClarifyAnswer, ClarifyResult
from app.schemas.pipeline import (
    BriefInput,
    PipelineResult,
    SceneDraft,
    SceneVisualPlan,
    ScriptDraft,
    Storyboard,
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


def build_storyboard_prompt(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
    clarifications: list[ClarifyAnswer] | None = None,
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


async def run_visual_plan(
    scene: SceneDraft, clarifications: list[ClarifyAnswer] | None = None
) -> SceneVisualPlan:
    result = await visual_dev_agent.run(build_visual_prompt(scene, clarifications), deps=scene)
    return result.output


async def run_storyboard(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
    clarifications: list[ClarifyAnswer] | None = None,
) -> Storyboard:
    result = await storyboard_agent.run(
        build_storyboard_prompt(
            script, visual_briefs, concept_specs, target_duration_sec, clarifications
        ),
        deps=target_duration_sec,
    )
    return result.output


# --------------------------------------------------------------------------- #
# full pipeline
# --------------------------------------------------------------------------- #


async def run_pipeline(
    brief_in: BriefInput, clarifications: list[ClarifyAnswer] | None = None
) -> PipelineResult:
    filled = await run_brief(brief_in.raw_prompt, clarifications)
    script = await run_script(filled, clarifications)

    plans = await asyncio.gather(
        *(run_visual_plan(scene, clarifications) for scene in script.scenes)
    )
    visual_briefs = [plan.visual_brief for plan in plans]
    concept_specs = [plan.concept_set for plan in plans]

    storyboard = await run_storyboard(
        script, visual_briefs, concept_specs, filled.target_duration_sec, clarifications
    )
    return PipelineResult(
        brief=filled,
        script=script,
        visual_briefs=visual_briefs,
        concept_specs=concept_specs,
        storyboard=storyboard,
    )
