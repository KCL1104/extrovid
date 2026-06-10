"""Storyboard agents: whole-board (legacy) and per-scene shot planning.

Both carry a duration budget as deps so an output validator can enforce that per-shot
durations roughly sum to it (retrying the model when they don't). The per-scene agent
is what the orchestrator fans out — no planner ever sees more than one scene.
"""

from pydantic_ai import Agent, ModelRetry, RunContext

from app.agents.prompts import SCENE_STORYBOARD_SYSTEM, STORYBOARD_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.pipeline import SceneShotPlan, Storyboard

DURATION_TOLERANCE = 0.25  # +/- 25% of target

storyboard_agent = Agent(
    get_model(),
    output_type=Storyboard,
    deps_type=int,  # target_duration_sec
    retries=2,
    system_prompt=STORYBOARD_SYSTEM,
)


@storyboard_agent.output_validator
async def _check_total_duration(ctx: RunContext[int], out: Storyboard) -> Storyboard:
    target = ctx.deps
    if target:
        total = out.total_duration_sec
        if abs(total - target) > DURATION_TOLERANCE * target:
            pct = int(DURATION_TOLERANCE * 100)
            raise ModelRetry(
                f"Total shot duration {total:.1f}s deviates more than {pct}% "
                f"from target {target}s. Re-balance per-shot durations."
            )
    return out


scene_storyboard_agent = Agent(
    get_model(),
    output_type=SceneShotPlan,
    deps_type=float,  # this scene's duration budget (sec)
    retries=2,
    system_prompt=SCENE_STORYBOARD_SYSTEM,
)


@scene_storyboard_agent.output_validator
async def _check_scene_duration(ctx: RunContext[float], out: SceneShotPlan) -> SceneShotPlan:
    budget = ctx.deps
    if budget:
        total = sum(s.duration_sec for s in out.shots)
        if abs(total - budget) > DURATION_TOLERANCE * budget:
            pct = int(DURATION_TOLERANCE * 100)
            raise ModelRetry(
                f"Scene shot durations sum to {total:.1f}s, deviating more than {pct}% "
                f"from the scene budget {budget:.1f}s. Re-balance per-shot durations."
            )
    return out
