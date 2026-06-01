"""Linear async planning pipeline: Brief -> Script -> Visual plans -> Storyboard.

Per-stage functions are exposed so the API can run a single stage; ``run_pipeline`` chains
them. This is intentionally a plain async chain — branching/routing (pydantic-graph) is a
later-phase concern.

Prompt builders embed machine-readable markers (TARGET_DURATION_SEC, SCENE_ORDER) so the
mock model stays consistent with the brief; real Qwen also benefits from the explicit cues.
"""

import asyncio

from app.agents.brief_agent import brief_agent
from app.agents.script_agent import script_agent
from app.agents.storyboard_agent import storyboard_agent
from app.agents.visual_dev_agent import visual_dev_agent
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


def build_script_prompt(brief: BriefInput) -> str:
    return (
        "Write a script for this brief.\n"
        f"Raw request: {brief.raw_prompt}\n"
        f"Product: {brief.product}\n"
        f"Story: {brief.story}\n"
        f"Platform: {brief.platform}\n"
        f"Style: {brief.style}\n"
        f"Audience: {brief.audience}\n"
        f"Target duration: {brief.target_duration_sec}s\n"
    )


def build_visual_prompt(scene: SceneDraft) -> str:
    beats = "; ".join(b.description for b in scene.beats)
    return (
        f"Develop the visual look for this scene. SCENE_ORDER={scene.order}\n"
        f"Title: {scene.title}\n"
        f"Summary: {scene.summary}\n"
        f"Beats: {beats}\n"
        "Use SCENE_ORDER for both the visual_brief.scene_order and concept_set.scene_order."
    )


def build_storyboard_prompt(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
) -> str:
    scene_lines = "\n".join(f"- scene {s.order} ({s.title}): {s.summary}" for s in script.scenes)
    return (
        "Turn this script into an executable shot list.\n"
        f"TARGET_DURATION_SEC={target_duration_sec}\n"
        f"Logline: {script.logline}\n"
        f"Scenes:\n{scene_lines}\n"
        f"Concept sets available: {len(concept_specs)}\n"
        "Produce 5-10 shots total, globally ordered from 0, durations summing near the target."
    )


# --------------------------------------------------------------------------- #
# per-stage runners
# --------------------------------------------------------------------------- #


async def run_brief(raw_prompt: str) -> BriefInput:
    result = await brief_agent.run(raw_prompt)
    return result.output


async def run_script(brief: BriefInput) -> ScriptDraft:
    result = await script_agent.run(build_script_prompt(brief), deps=brief)
    return result.output


async def run_visual_plan(scene: SceneDraft) -> SceneVisualPlan:
    result = await visual_dev_agent.run(build_visual_prompt(scene), deps=scene)
    return result.output


async def run_storyboard(
    script: ScriptDraft,
    visual_briefs: list,
    concept_specs: list[VisualConceptSetSpec],
    target_duration_sec: int,
) -> Storyboard:
    result = await storyboard_agent.run(
        build_storyboard_prompt(script, visual_briefs, concept_specs, target_duration_sec),
        deps=target_duration_sec,
    )
    return result.output


# --------------------------------------------------------------------------- #
# full pipeline
# --------------------------------------------------------------------------- #


async def run_pipeline(brief_in: BriefInput) -> PipelineResult:
    filled = await run_brief(brief_in.raw_prompt)
    script = await run_script(filled)

    plans = await asyncio.gather(*(run_visual_plan(scene) for scene in script.scenes))
    visual_briefs = [plan.visual_brief for plan in plans]
    concept_specs = [plan.concept_set for plan in plans]

    storyboard = await run_storyboard(
        script, visual_briefs, concept_specs, filled.target_duration_sec
    )
    return PipelineResult(
        brief=filled,
        script=script,
        visual_briefs=visual_briefs,
        concept_specs=concept_specs,
        storyboard=storyboard,
    )
