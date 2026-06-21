"""Optional LLM-as-judge for the eval: narrative coherence of the planned script.

Thin wrapper over the SAME production judge the pipeline's best-of-N uses
(app.agents.script_review_agent), so the eval reports exactly what the engine optimizes for.
Returns None under mock.
"""

from __future__ import annotations

from app.agents.script_review_agent import ScriptCoherence, review_script_coherence
from app.schemas.pipeline import PipelineResult


async def judge_coherence(result: PipelineResult) -> ScriptCoherence | None:
    return await review_script_coherence(result.script)
