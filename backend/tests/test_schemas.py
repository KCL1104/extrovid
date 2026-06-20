"""Lock the pipeline schemas: every acceptance rule from the spec is asserted here."""

import pytest
from pydantic import ValidationError

from app.models.enums import (
    MAX_SCENES,
    MAX_TARGET_DURATION_SEC,
    AspectRatio,
    ConceptSetType,
    PreferredModel,
)
from app.schemas.pipeline import (
    BriefInput,
    CameraSpec,
    PerformanceSpec,
    PlannedLookFrame,
    SceneBeat,
    SceneDraft,
    SceneVisualPlan,
    ScriptDraft,
    ShotDTO,
    Storyboard,
    StoryboardScene,
    VisualBrief,
    VisualConceptSetSpec,
)

# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #


def make_shot(
    order: int,
    *,
    scene_order: int = 0,
    model: PreferredModel = PreferredModel.T2V,
    duration: float = 3.0,
) -> ShotDTO:
    return ShotDTO(
        order=order,
        scene_order=scene_order,
        purpose="establish the product",
        duration_sec=duration,
        beat="hero shot",
        camera_spec=CameraSpec(shot_size="MS", angle="eye-level", movement="static"),
        performance_spec=PerformanceSpec(subject="cup", action="steams gently"),
        preferred_model=model,
        acceptance_rules=["product clearly in frame"],
    )


def make_storyboard(n_shots: int) -> Storyboard:
    shots = [make_shot(i) for i in range(n_shots)]
    return Storyboard(scenes=[StoryboardScene(scene_order=0, shots=shots)])


def make_frame(*, selected: bool = False) -> PlannedLookFrame:
    return PlannedLookFrame(
        prompt="warm cinematic coffee cup", type=ConceptSetType.STYLE, selected=selected
    )


def make_concept_set(
    n_frames: int, *, n_selected: int = 0, scene_order: int = 0
) -> VisualConceptSetSpec:
    frames = [make_frame(selected=(i < n_selected)) for i in range(n_frames)]
    return VisualConceptSetSpec(
        scene_order=scene_order,
        brief="warm look",
        type=ConceptSetType.STYLE,
        candidate_look_frames=frames,
    )


def make_visual_brief(scene_order: int = 0) -> VisualBrief:
    return VisualBrief(
        scene_order=scene_order,
        visual_style="cinematic",
        mood="warm",
        palette=["#3b2f2f", "#d9a066"],
        lighting="golden hour",
        camera_language="slow push-ins",
    )


# --------------------------------------------------------------------------- #
# Storyboard: shot count + contiguous global order
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", [1, 4, 5, 6, 10])
def test_storyboard_valid_shot_counts(n):
    sb = make_storyboard(n)
    assert len(sb.all_shots) == n
    assert sb.total_duration_sec == pytest.approx(3.0 * n)


@pytest.mark.parametrize("n", [0, 11, 15])  # >10 violates the per-scene cap
def test_storyboard_rejects_out_of_bounds_shot_count(n):
    with pytest.raises(ValidationError):
        make_storyboard(n)


def test_storyboard_rejects_non_contiguous_order():
    shots = [make_shot(0), make_shot(1), make_shot(2), make_shot(3), make_shot(5)]  # gap at 4
    with pytest.raises(ValidationError, match="contiguous"):
        Storyboard(scenes=[StoryboardScene(scene_order=0, shots=shots)])


def test_storyboard_rejects_duplicate_order():
    shots = [make_shot(0), make_shot(1), make_shot(2), make_shot(3), make_shot(3)]
    with pytest.raises(ValidationError):
        Storyboard(scenes=[StoryboardScene(scene_order=0, shots=shots)])


def test_storyboard_contiguous_order_across_multiple_scenes():
    s0 = StoryboardScene(scene_order=0, shots=[make_shot(0), make_shot(1, scene_order=0)])
    s1 = StoryboardScene(
        scene_order=1,
        shots=[
            make_shot(2, scene_order=1),
            make_shot(3, scene_order=1),
            make_shot(4, scene_order=1),
        ],
    )
    sb = Storyboard(scenes=[s0, s1])
    assert len(sb.all_shots) == 5


# --------------------------------------------------------------------------- #
# ShotDTO: model routing + duration
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("model", [PreferredModel.T2V, PreferredModel.I2V, PreferredModel.R2V])
def test_shot_allows_plannable_models(model):
    assert make_shot(0, model=model).preferred_model == model


def test_shot_rejects_videoedit():
    with pytest.raises(ValidationError, match="only routes"):
        make_shot(0, model=PreferredModel.VIDEOEDIT)


@pytest.mark.parametrize("dur", [0, -1, 15.1, 30])
def test_shot_rejects_bad_duration(dur):
    with pytest.raises(ValidationError):
        make_shot(0, duration=dur)


# --------------------------------------------------------------------------- #
# VisualConceptSetSpec: frame count + selection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", [4, 5, 8])
def test_concept_set_valid_frame_counts(n):
    assert len(make_concept_set(n).candidate_look_frames) == n


@pytest.mark.parametrize("n", [0, 3, 9, 12])
def test_concept_set_rejects_out_of_bounds_frames(n):
    with pytest.raises(ValidationError):
        make_concept_set(n)


def test_concept_set_allows_at_most_one_selected():
    assert make_concept_set(4, n_selected=1)  # ok
    with pytest.raises(ValidationError, match="one look frame"):
        make_concept_set(4, n_selected=2)


def test_planned_look_frame_image_asset_id_defaults_none():
    assert make_frame().image_asset_id is None


# --------------------------------------------------------------------------- #
# ScriptDraft + SceneVisualPlan
# --------------------------------------------------------------------------- #


def _scene(order: int) -> SceneDraft:
    return SceneDraft(
        order=order,
        title="t",
        summary="s",
        beats=[SceneBeat(order=0, description="d")],
        est_duration_sec=5.0,
    )


def test_script_rejects_duplicate_scene_order():
    with pytest.raises(ValidationError, match="unique"):
        ScriptDraft(logline="x", scenes=[_scene(0), _scene(0)])


def test_script_rejects_too_many_scenes():
    with pytest.raises(ValidationError):
        ScriptDraft(logline="x", scenes=[_scene(i) for i in range(MAX_SCENES + 1)])


def test_scene_visual_plan_requires_matching_scene_order():
    brief = make_visual_brief(scene_order=0)
    cs = make_concept_set(4, scene_order=1)
    with pytest.raises(ValidationError, match="scene_order"):
        SceneVisualPlan(visual_brief=brief, concept_set=cs)


def test_scene_visual_plan_ok_when_orders_match():
    plan = SceneVisualPlan(
        visual_brief=make_visual_brief(2), concept_set=make_concept_set(4, scene_order=2)
    )
    assert plan.concept_set.scene_order == 2


# --------------------------------------------------------------------------- #
# BriefInput
# --------------------------------------------------------------------------- #


def test_brief_requires_raw_prompt():
    with pytest.raises(ValidationError):
        BriefInput(raw_prompt="")


@pytest.mark.parametrize("dur", [4, MAX_TARGET_DURATION_SEC + 1, 0])
def test_brief_rejects_bad_duration(dur):
    with pytest.raises(ValidationError):
        BriefInput(raw_prompt="x", target_duration_sec=dur)


def test_brief_defaults():
    b = BriefInput(raw_prompt="a 30s vertical coffee ad")
    assert b.target_duration_sec == 20
    assert b.aspect_ratio == AspectRatio.R9_16
    assert b.platform == "generic"
