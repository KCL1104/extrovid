"""Deterministic agent tests — all offline via the mock model (USE_MOCK_LLM=true)."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.brief_agent import brief_agent
from app.agents.storyboard_agent import storyboard_agent
from app.schemas.pipeline import BriefInput, Storyboard


def _sb_args(n_shots: int, target: int) -> dict:
    """Build a storyboard args dict with contiguous order and durations summing to target."""
    base = round(target / n_shots, 2)
    durations = [base] * n_shots
    durations[-1] = round(target - base * (n_shots - 1), 2)
    durations = [min(15.0, max(0.5, d)) for d in durations]
    shots = [
        {
            "order": i,
            "scene_order": 0,
            "purpose": "p",
            "duration_sec": durations[i],
            "beat": "b",
            "camera_spec": {"shot_size": "MS", "angle": "eye-level", "movement": "static"},
            "performance_spec": {"subject": "x", "action": "y"},
            "preferred_model": "wan2.7-t2v",
            "acceptance_rules": ["r"],
            "reference_look_frame_ids": [],
            "transition": "cut",
        }
        for i in range(n_shots)
    ]
    return {"scenes": [{"scene_order": 0, "shots": shots}]}


async def test_brief_agent_returns_filled_brief():
    result = await brief_agent.run("a 15s vertical ad for sneakers")
    brief = result.output
    assert isinstance(brief, BriefInput)
    assert brief.target_duration_sec == 15  # parsed from "15s" by the mock
    assert brief.raw_prompt


async def test_storyboard_agent_recovers_via_model_retry():
    """First model response is invalid (12 shots); after a ModelRetry the second is valid."""
    calls = {"n": 0}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        n_shots = 12 if calls["n"] == 1 else 6  # 12 fails the 5..10 rule, 6 passes
        name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=_sb_args(n_shots, 20))])

    with storyboard_agent.override(model=FunctionModel(fn)):
        result = await storyboard_agent.run("TARGET_DURATION_SEC=20", deps=20)

    sb = result.output
    assert isinstance(sb, Storyboard)
    assert len(sb.all_shots) == 6
    assert calls["n"] == 2  # one bad attempt + one good


async def test_storyboard_agent_exhausts_retries_on_persistent_invalid():
    def fn(messages, info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=_sb_args(12, 20))])

    with storyboard_agent.override(model=FunctionModel(fn)):
        with pytest.raises(UnexpectedModelBehavior):  # retries exhausted
            await storyboard_agent.run("TARGET_DURATION_SEC=20", deps=20)


async def test_storyboard_agent_duration_validator_triggers_retry_then_fails():
    """A schema-valid storyboard whose durations are far from target must be rejected."""

    def fn(messages, info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name
        # 6 shots that sum to ~6s while target is 60s -> >25% off, output_validator retries
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=_sb_args(6, 6))])

    with storyboard_agent.override(model=FunctionModel(fn)):
        with pytest.raises(UnexpectedModelBehavior):
            await storyboard_agent.run("TARGET_DURATION_SEC=60", deps=60)
