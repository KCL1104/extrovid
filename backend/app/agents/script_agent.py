"""ScriptAgent: structured brief -> ScriptDraft (logline + scene beats)."""

from pydantic_ai import Agent

from app.agents.prompts import SCRIPT_SYSTEM
from app.core.config import get_settings
from app.providers.model_factory import get_model
from app.schemas.pipeline import BriefInput, ScriptDraft

# Script writing is the most creative step in the pipeline → flagship model (qwen_script_model,
# default qwen3.7-max). Every other agent keeps the balanced qwen_model.
script_agent = Agent(
    get_model(get_settings().qwen_script_model),
    output_type=ScriptDraft,
    deps_type=BriefInput,
    retries=2,
    system_prompt=SCRIPT_SYSTEM,
)
