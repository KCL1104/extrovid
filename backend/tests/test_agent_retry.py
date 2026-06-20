"""run_agent: whole-conversation retry that clears the Qwen empty-tool-arguments poison.

Regression for the prod 500 on POST /visual-briefs (2026-06-20): qwen3.7-plus emitted a
structured-output tool call with empty ``function.arguments``; pydantic_ai's in-run retry
replayed that poisoned turn and DashScope rejected the history with
``400 InternalError.Algo.InvalidParameter: The "function.arguments" ... must be in JSON``.
"""

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from app.core.agent_run import run_agent
from app.core.config import get_settings
from app.pipeline.orchestrator import run_pipeline
from app.schemas.pipeline import BriefInput


def _qwen_arg_400() -> ModelHTTPError:
    """The exact production error: DashScope rejects the replayed empty-args history."""
    return ModelHTTPError(
        status_code=400,
        model_name="qwen3.7-plus",
        body={
            "message": '<400> InternalError.Algo.InvalidParameter: The "function.arguments" '
            "parameter of the code model must be in JSON format.",
            "code": "invalid_parameter_error",
        },
    )


class _StubAgent:
    """Minimal duck-typed agent: ``.run`` raises queued errors, then returns a sentinel."""

    def __init__(self, errors):
        self._errors = list(errors)
        self.calls = 0

    async def run(self, *args, **kwargs):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return "OK"


@pytest.fixture
def fast_retry():
    s = get_settings()
    prev_delay, prev_retries = s.http_retry_base_sec, s.llm_retries
    s.http_retry_base_sec, s.llm_retries = 0.0, 2
    yield s
    s.http_retry_base_sec, s.llm_retries = prev_delay, prev_retries


async def test_recovers_from_qwen_empty_args_400(fast_retry):
    agent = _StubAgent([_qwen_arg_400()])  # poisoned once, then a fresh run succeeds
    out = await run_agent(agent, "prompt")
    assert out == "OK"
    assert agent.calls == 2


async def test_recovers_from_unexpected_model_behavior(fast_retry):
    # IncompleteToolCall (subclass) and other unparseable tool calls surface as this
    agent = _StubAgent([UnexpectedModelBehavior("could not parse tool call output")])
    out = await run_agent(agent, "prompt")
    assert out == "OK"
    assert agent.calls == 2


async def test_retryable_5xx_recovers(fast_retry):
    agent = _StubAgent([ModelHTTPError(status_code=503, model_name="qwen3.7-plus", body={})])
    out = await run_agent(agent, "prompt")
    assert out == "OK"
    assert agent.calls == 2


async def test_first_try_success_no_retry(fast_retry):
    agent = _StubAgent([])
    out = await run_agent(agent, "prompt")
    assert out == "OK"
    assert agent.calls == 1


async def test_plain_400_not_retried(fast_retry):
    # a 400 WITHOUT the invalid-parameter / function.arguments signature is a real bad
    # request — retrying it is pointless, so it must surface immediately
    err = ModelHTTPError(
        status_code=400,
        model_name="qwen3.7-plus",
        body={"message": "missing required field", "code": "bad_request"},
    )
    agent = _StubAgent([err, err, err])
    with pytest.raises(ModelHTTPError):
        await run_agent(agent, "prompt")
    assert agent.calls == 1


async def test_auth_401_not_retried(fast_retry):
    err = ModelHTTPError(status_code=401, model_name="qwen3.7-plus", body={"message": "bad key"})
    agent = _StubAgent([err])
    with pytest.raises(ModelHTTPError):
        await run_agent(agent, "prompt")
    assert agent.calls == 1


async def test_exhausts_retries_then_raises_last(fast_retry):
    # persistent retryable error -> attempts == llm_retries + 1 == 3, then raise
    agent = _StubAgent([_qwen_arg_400()] * 5)
    with pytest.raises(ModelHTTPError):
        await run_agent(agent, "prompt")
    assert agent.calls == 3


async def test_pipeline_recovers_from_one_poisoned_visual_plan(monkeypatch, fast_retry):
    """End-to-end: one scene's visual-plan call hits the Qwen 400, yet the full pipeline
    still yields a complete storyboard — proving run_visual_plan is wired through run_agent."""
    from app.agents.visual_dev_agent import visual_dev_agent

    original_run = visual_dev_agent.run
    state = {"poisoned": False}

    async def flaky_run(*args, **kwargs):
        if not state["poisoned"]:
            state["poisoned"] = True
            raise _qwen_arg_400()
        return await original_run(*args, **kwargs)

    monkeypatch.setattr(visual_dev_agent, "run", flaky_run)

    result = await run_pipeline(BriefInput(raw_prompt="a 20s teaser"))
    assert state["poisoned"] is True  # the injected failure actually fired
    assert len(result.visual_briefs) == len(result.script.scenes)  # and the pipeline recovered
