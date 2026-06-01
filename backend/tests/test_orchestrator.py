"""Golden-path test: a brief becomes a schema-valid storyboard, fully offline (mock model)."""

import pytest

from app.agents.storyboard_agent import DURATION_TOLERANCE
from app.models.enums import MAX_SHOTS, MIN_SHOTS, PLANNABLE_MODELS_M1
from app.pipeline.orchestrator import run_pipeline
from app.schemas.pipeline import BriefInput, PipelineResult


async def test_golden_path_brief_to_storyboard():
    result = await run_pipeline(
        BriefInput(raw_prompt="a 30s vertical product ad for a coffee brand")
    )
    assert isinstance(result, PipelineResult)

    # brief parsed target from "30s"
    target = result.brief.target_duration_sec
    assert target == 30

    sb = result.storyboard
    shots = sb.all_shots
    assert MIN_SHOTS <= len(shots) <= MAX_SHOTS
    # contiguous global order is guaranteed by the schema validator; re-assert here
    assert sorted(s.order for s in shots) == list(range(len(shots)))
    assert all(0 < s.duration_sec <= 15 for s in shots)
    assert all(s.preferred_model in PLANNABLE_MODELS_M1 for s in shots)
    assert abs(sb.total_duration_sec - target) <= DURATION_TOLERANCE * target

    # one concept set per scene; each 4-8 planned frames with no image asset (M1)
    assert len(result.concept_specs) == len(result.script.scenes)
    assert len(result.visual_briefs) == len(result.script.scenes)
    for cs in result.concept_specs:
        assert 4 <= len(cs.candidate_look_frames) <= 8
        assert all(f.image_asset_id is None for f in cs.candidate_look_frames)

    # visual brief and concept set scene_orders line up with the script scenes
    scene_orders = {s.order for s in result.script.scenes}
    assert {cs.scene_order for cs in result.concept_specs} == scene_orders


@pytest.mark.parametrize(
    "raw,expected_target",
    [
        ("a 15 second teaser", 15),
        ("60s brand film", 60),
        ("make something cool", 20),  # no duration -> mock default
    ],
)
async def test_pipeline_respects_parsed_duration(raw, expected_target):
    result = await run_pipeline(BriefInput(raw_prompt=raw))
    assert result.brief.target_duration_sec == expected_target
    assert abs(result.storyboard.total_duration_sec - expected_target) <= 0.25 * expected_target
