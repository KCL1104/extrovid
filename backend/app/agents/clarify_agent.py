"""ClarifyAgent: assess a raw video idea and propose at most 4 director-style questions.

Stateless plan-stage triage — the output is never persisted; answers the user gives are
folded back into the prompt fed to the BriefAgent (see ``orchestrator.fold_clarifications``).
"""

from pydantic_ai import Agent

from app.agents.prompts import CLARIFY_SYSTEM
from app.providers.model_factory import get_model
from app.schemas.api import ClarifyResult

clarify_agent = Agent(
    get_model(),
    output_type=ClarifyResult,
    retries=1,
    system_prompt=CLARIFY_SYSTEM,
)
