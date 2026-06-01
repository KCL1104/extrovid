"""ScriptAgent: structured brief -> ScriptDraft (logline + scene beats)."""

from pydantic_ai import Agent

from app.agents.prompts import SCRIPT_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.pipeline import BriefInput, ScriptDraft

script_agent = Agent(
    get_model(),
    output_type=ScriptDraft,
    deps_type=BriefInput,
    retries=2,
    system_prompt=SCRIPT_SYSTEM,
)
