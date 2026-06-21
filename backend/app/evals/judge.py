"""Optional LLM-as-judge: scores narrative coherence of the planned script.

Meaningful only against the REAL LLM — on mock the canned output isn't worth judging, so the
judge returns None in mock mode (the structural metrics carry the eval there). No mock_data
wiring needed by construction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.core.config import get_settings
from app.providers.model_factory import get_model
from app.schemas.pipeline import PipelineResult

JUDGE_SYSTEM = (
    "You are a story editor reviewing a short video's planned script. Judge ONLY narrative "
    "coherence: do the scenes follow a clear through-line, escalate or develop, and resolve? "
    "Is anything contradictory, repetitive, or a non-sequitur? Be a tough but fair editor. "
    "Score 0-10 (10 = airtight, 5 = watchable but loose, <=3 = incoherent) and list concrete "
    "issues (empty if none)."
)


class CoherenceVerdict(BaseModel):
    coherence: float = Field(..., ge=0, le=10)
    issues: list[str] = Field(default_factory=list, max_length=6)


def _render(result: PipelineResult) -> str:
    lines = [f"LOGLINE: {result.script.logline}", "", "SCENES:"]
    for sc in sorted(result.script.scenes, key=lambda s: s.order):
        lines.append(f"{sc.order + 1}. {sc.title} — {sc.summary}")
        for b in sc.beats:
            lines.append(f"   - {b.description}")
    return "\n".join(lines)


async def judge_coherence(result: PipelineResult) -> CoherenceVerdict | None:
    if get_settings().use_mock_llm:
        return None  # judge needs the real model to mean anything
    agent = Agent(
        get_model(),
        output_type=CoherenceVerdict,
        system_prompt=JUDGE_SYSTEM,
        retries=get_settings().llm_retries,
    )
    out = await agent.run(_render(result))
    return out.output
