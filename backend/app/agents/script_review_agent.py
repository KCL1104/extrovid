"""Script coherence judge — scores a ScriptDraft's narrative through-line (0-10 + issues).

Two uses: (1) the pipeline's best-of-N script selection picks the highest-coherence draft to
tame run-to-run variance; (2) the eval harness reports the same score. Meaningful only against
the real LLM — ``review_script_coherence`` returns None under mock (the canned script isn't
worth judging), so offline tests and the one-prompt-to-video mock path are untouched.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.core.agent_run import run_agent
from app.core.config import get_settings
from app.providers.model_factory import get_model
from app.schemas.pipeline import ScriptDraft

SCRIPT_COHERENCE_SYSTEM = (
    "You are a story editor reviewing a short video's planned script. Judge ONLY narrative "
    "coherence: do the scenes follow a clear through-line, develop or escalate, and resolve? "
    "Is anything contradictory, repetitive, or a non-sequitur? Be a tough but fair editor. "
    "Score 0-10 (10 = airtight, 5 = watchable but loose, <=3 = incoherent) and list concrete "
    "issues (empty if none)."
)


class ScriptCoherence(BaseModel):
    coherence: float = Field(..., ge=0, le=10)
    issues: list[str] = Field(default_factory=list, max_length=6)


script_review_agent = Agent(
    get_model(),
    output_type=ScriptCoherence,
    system_prompt=SCRIPT_COHERENCE_SYSTEM,
    retries=get_settings().llm_retries,
)


def render_script(script: ScriptDraft) -> str:
    lines = [f"LOGLINE: {script.logline}", "", "SCENES:"]
    for sc in sorted(script.scenes, key=lambda s: s.order):
        lines.append(f"{sc.order + 1}. {sc.title} — {sc.summary}")
        for b in sc.beats:
            lines.append(f"   - {b.description}")
    return "\n".join(lines)


async def review_script_coherence(script: ScriptDraft) -> ScriptCoherence | None:
    """None under mock — the canned script isn't worth judging."""
    if get_settings().use_mock_llm:
        return None
    result = await run_agent(script_review_agent, render_script(script))
    return result.output
