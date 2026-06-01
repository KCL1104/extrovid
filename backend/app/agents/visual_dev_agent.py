"""VisualDevelopmentAgent: a scene -> SceneVisualPlan (visual brief + concept set spec)."""

from pydantic_ai import Agent

from app.agents.prompts import VISUAL_DEV_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.pipeline import SceneDraft, SceneVisualPlan

visual_dev_agent = Agent(
    get_model(),
    output_type=SceneVisualPlan,
    deps_type=SceneDraft,
    retries=2,
    system_prompt=VISUAL_DEV_SYSTEM,
)
