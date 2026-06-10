"""CastAgent: script -> planned cast (CharacterProfile rows).

Adopted from ViMax's CharacterExtractor doctrine (docs/vimax-research.md B2): features
must be visualizable-only (static face/body vs dynamic wardrobe split), invented
plausibly when the script is silent, and visually distinct across the cast. Profiles
created here feed the existing r2v cast-lock + portrait-sheet machinery.
"""

from pydantic_ai import Agent

from app.agents.prompts import CAST_SYSTEM
from app.core.config import get_settings
from app.providers.model_factory import get_model
from app.schemas.pipeline import CastList

cast_agent = Agent(
    get_model(),
    output_type=CastList,
    system_prompt=CAST_SYSTEM,
    retries=get_settings().llm_retries,
)
