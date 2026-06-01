"""StoryboardAgent: script + visuals -> Storyboard (executable shot list).

Carries the target duration as deps so an output validator can enforce that per-shot
durations roughly sum to the brief's target (retrying the model when they don't).
"""

from pydantic_ai import Agent, ModelRetry, RunContext

from app.agents.prompts import STORYBOARD_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.pipeline import Storyboard

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
