"""ReviseAgents: targeted, schema-preserving revision of one planning artifact.

ViMax revises artifacts by whole-file LLM rewrite and has to beg the model to
"preserve valid JSON and the existing schema shape"; PydanticAI structured output
gives the same operation with validation for free (docs/vimax-research.md D2).
"""

from pydantic_ai import Agent

from app.core.config import get_settings
from app.providers.model_factory import get_model
from app.schemas.pipeline import SceneDraft, ShotDTO, VisualBrief

REVISE_SYSTEM = """You revise ONE planning artifact of an AI video production.
You are given the artifact's current value as JSON and a revision instruction.
Apply the instruction exactly. Preserve the existing schema shape and every field the
instruction does not cover — do not improve, expand, or rewrite anything unasked.
Keep identifiers (order, scene_order) unchanged unless the instruction says otherwise.
Return only the structured object."""

revise_scene_agent = Agent(
    get_model(),
    output_type=SceneDraft,
    system_prompt=REVISE_SYSTEM,
    retries=get_settings().llm_retries,
)

revise_visual_agent = Agent(
    get_model(),
    output_type=VisualBrief,
    system_prompt=REVISE_SYSTEM,
    retries=get_settings().llm_retries,
)

revise_shot_agent = Agent(
    get_model(),
    output_type=ShotDTO,
    system_prompt=REVISE_SYSTEM,
    retries=get_settings().llm_retries,
)
