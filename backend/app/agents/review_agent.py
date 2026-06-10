"""ReviewAgent: evaluates a finished ShotVersion against its shot's acceptance rules.

Activates the spec's review loop — every generated take gets an AI score, director-style
notes, and concrete revision suggestions (each suggestion is a ready-to-run ``videoedit``
instruction or a retake recommendation). Output schema lives here (not in
``app.schemas.pipeline``) because it is an execution-time contract, not a planning one.
"""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.prompts import REVIEW_SYSTEM
from app.core.config import get_settings
from app.providers.model_factory import get_model


class ReviewSuggestion(BaseModel):
    """One actionable fix. ``edit`` suggestions are valid wan2.7-videoedit instructions."""

    kind: Literal["edit", "retake"] = "edit"
    instruction: str = Field(..., min_length=1)


class ReviewResult(BaseModel):
    verdict: Literal["pass", "revise"]
    score: float = Field(..., ge=0, le=10, description="0-10 director's score for the take.")
    notes: list[str] = Field(..., min_length=1, description="Short director-style review notes.")
    suggestions: list[ReviewSuggestion] = Field(default_factory=list, max_length=3)
    continuity_notes: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Cross-shot drift vs the previous shot's frame (wardrobe, identity, "
        "palette, flipped blocking). Empty when nothing drifts.",
    )


review_agent = Agent(
    get_model(),
    output_type=ReviewResult,
    system_prompt=REVIEW_SYSTEM,
    retries=get_settings().llm_retries,
)
