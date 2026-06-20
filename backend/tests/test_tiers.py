"""Length tiers (P0): duration -> tier mapping + tier-aware planning prompt injection."""

import pytest

from app.agents.tiers import (
    Tier,
    scene_shot_tier_block,
    script_tier_block,
    tier_for,
)
from app.pipeline.orchestrator import (
    build_scene_storyboard_prompt,
    build_script_prompt,
    run_pipeline,
)
from app.schemas.pipeline import BriefInput, SceneBeat, SceneDraft


@pytest.mark.parametrize(
    "sec,expected",
    [
        (None, Tier.SHORT),
        (0, Tier.SHORT),
        (5, Tier.SHORT),
        (20, Tier.SHORT),
        (90, Tier.SHORT),  # inclusive upper bound
        (91, Tier.MEDIUM),
        (180, Tier.MEDIUM),
        (300, Tier.MEDIUM),  # inclusive upper bound
        (301, Tier.LONG),
        (600, Tier.LONG),
        (1200, Tier.LONG),
    ],
)
def test_tier_boundaries(sec, expected):
    assert tier_for(sec) is expected


def test_script_tier_block_is_tier_specific():
    short = script_tier_block(Tier.SHORT, 20)
    medium = script_tier_block(Tier.MEDIUM, 180)
    long = script_tier_block(Tier.LONG, 480)

    assert "FORMAT TIER: short" in short
    assert "HOOK" in short and "PAYOFF" in short
    assert "FORMAT TIER: medium" in medium
    assert "call-to-action" in medium or "resolution" in medium
    assert "FORMAT TIER: long" in long
    assert "acts/chapters" in long
    # the soft scene-count range differs by tier
    assert "1-3 scenes" in short
    assert "3-6 scenes" in medium
    assert "6-12 scenes" in long


def _scene(order: int = 0) -> SceneDraft:
    return SceneDraft(
        order=order,
        title="Hook",
        summary="open on the problem",
        beats=[SceneBeat(order=0, description="establish the tension")],
        est_duration_sec=10,
    )


def test_scene_shot_block_hook_only_for_short_scene_zero():
    assert "HOOK" in scene_shot_tier_block(Tier.SHORT, 10, scene_order=0)
    assert "HOOK" not in scene_shot_tier_block(Tier.SHORT, 10, scene_order=1)
    assert "HOOK" not in scene_shot_tier_block(Tier.MEDIUM, 60, scene_order=0)
    # every tier still carries pacing/ASL guidance
    for tier in Tier:
        assert "PACING" in scene_shot_tier_block(tier, 30, scene_order=2)


def test_script_prompt_carries_the_tier():
    p_short = build_script_prompt(BriefInput(raw_prompt="x", target_duration_sec=20))
    p_long = build_script_prompt(BriefInput(raw_prompt="x", target_duration_sec=480))
    assert "FORMAT TIER: short" in p_short
    assert "FORMAT TIER: long" in p_long


def test_scene_prompt_tier_is_opt_in_and_backcompat():
    # no tier -> no pacing block (preserves the legacy 3-arg call sites)
    assert "PACING" not in build_scene_storyboard_prompt(_scene(), None, 10)
    assert "PACING" in build_scene_storyboard_prompt(_scene(), None, 10, tier=Tier.MEDIUM)


async def test_long_brief_routes_to_long_tier_and_plans_per_scene():
    result = await run_pipeline(BriefInput(raw_prompt="a 400s brand documentary"))
    assert result.brief.target_duration_sec == 400
    assert tier_for(result.brief.target_duration_sec) is Tier.LONG
    shots = result.storyboard.all_shots
    assert len(shots) > 10  # per-scene fold, past the old global ceiling
    assert sorted(s.order for s in shots) == list(range(len(shots)))
    assert all(0 < s.duration_sec <= 15 for s in shots)
