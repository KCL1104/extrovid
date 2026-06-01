"""BriefAgent: free text -> filled, structured BriefInput."""

from pydantic_ai import Agent

from app.agents.prompts import BRIEF_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.pipeline import BriefInput

brief_agent = Agent(
    get_model(),
    output_type=BriefInput,
    retries=1,
    system_prompt=BRIEF_SYSTEM,
)
