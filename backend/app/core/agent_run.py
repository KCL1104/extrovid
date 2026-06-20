"""Re-run a pydantic_ai agent from a *fresh* conversation on transient model failures.

The Qwen/DashScope models occasionally emit a structured-output (or function) tool call
whose ``arguments`` field is an empty string / non-JSON. pydantic_ai's *in-run* retry
(``Agent(retries=...)``) then replays that malformed assistant turn in the follow-up
request, and DashScope rejects the entire history with::

    400 InternalError.Algo.InvalidParameter:
    The "function.arguments" parameter of the code model must be in JSON format.

The in-run retry can't recover — the poison lives in the conversation it keeps reusing.
This helper retries the whole ``agent.run`` from scratch, so the bad turn is gone and the
model (sampling, not deterministic) almost always produces valid arguments next time.

Safe ONLY for agents whose tools have no external side effects — the pure planning /
transform agents. NEVER wrap the director: its tools mutate the project, so a whole-run
retry would double-apply actions.
"""

import asyncio
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from app.core.config import get_settings
from app.core.logging import log

# DashScope/Qwen rate limits + 5xx are transient. A 400 carrying the invalid-parameter /
# function.arguments signature is the empty-tool-arguments replay bug (see module docstring),
# which a fresh conversation clears.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    # IncompleteToolCall subclasses UnexpectedModelBehavior — the model produced an
    # unusable tool call; a fresh run is the recovery path.
    if isinstance(exc, UnexpectedModelBehavior):
        return True
    if isinstance(exc, ModelHTTPError):
        if exc.status_code in _RETRYABLE_STATUS:
            return True
        if exc.status_code == 400:
            blob = f"{exc.body} {exc}".lower()
            return "function.arguments" in blob or "invalid_parameter" in blob
    return False


async def run_agent(agent: Agent, *args: Any, **kwargs: Any) -> AgentRunResult:
    """``agent.run(...)`` with whole-run retry on transient Qwen tool-call failures.

    Each attempt is a brand-new conversation — the only reliable way to clear the
    empty-``function.arguments`` poison that pydantic_ai's in-run retry keeps replaying.
    Backoff reuses ``http_retry_base_sec``; attempt count is ``llm_retries`` + 1. Use for
    side-effect-free planning agents only (never the director).
    """
    s = get_settings()
    attempts = s.llm_retries + 1
    delay = s.http_retry_base_sec
    for attempt in range(attempts):
        try:
            return await agent.run(*args, **kwargs)
        except (ModelHTTPError, UnexpectedModelBehavior) as exc:
            if not _is_retryable(exc) or attempt == attempts - 1:
                raise
            log.warning(
                "agent.retry attempt=%d/%d error=%s",
                attempt + 1,
                attempts,
                str(exc)[:200],
            )
            await asyncio.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")  # pragma: no cover
