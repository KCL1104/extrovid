"""OutlineAgent: brief -> ActOutline (the LONG-tier chapter structure above scenes)."""

from pydantic_ai import Agent

from app.agents.prompts import ACT_OUTLINE_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.pipeline import ActOutline

outline_agent = Agent(
    get_model(),
    output_type=ActOutline,
    retries=2,
    system_prompt=ACT_OUTLINE_SYSTEM,
)
