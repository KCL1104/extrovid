"""The eval harness runs end-to-end and produces a scorecard (offline, mock pipeline)."""

from app.evals import metrics as metrics_mod
from app.evals.golden import Golden
from app.evals.run import _evaluate_one, render_report


async def test_eval_scores_a_mock_plan_end_to_end():
    g = Golden("t", "a 20s coffee teaser in a small cafe", 20, expect_cast=False)
    row = await _evaluate_one(g, with_judge=False)
    assert "error" not in row, row.get("error")
    s = row["scored"]
    assert 0 <= s["overall"] <= 100
    assert s["totals"]["shots"] > 0
    keys = {m.key for m in s["metrics"]}
    assert {
        "duration_adherence",
        "keyframe_contract",
        "camera_continuity",
        "cast_integrity",
    } <= keys
    # every metric score is a sane fraction
    for m in s["metrics"]:
        assert 0.0 <= m.score <= 1.0


async def test_report_renders_markdown():
    g = Golden("coffee", "a 20s coffee teaser", 20, expect_cast=False)
    row = await _evaluate_one(g, with_judge=True)  # judge skipped under mock -> verdict None
    md = render_report([row], judged=True)
    assert "# Quality eval" in md
    assert "coffee" in md
    assert "Human spot-check" in md
    assert "judge skipped" in md  # mock path message


def test_duration_adherence_penalises_drift():
    # pure-metric guard: perfect vs way-off duration must score very differently
    from types import SimpleNamespace as NS

    def fake(planned, target):
        shots = [
            NS(
                duration_sec=planned,
                scene_order=0,
                camera_id=0,
                character_name=None,
                dialogue=None,
                speaker=None,
                first_frame_desc="a",
                last_frame_desc="b",
                motion_desc="c",
                screen_direction=None,
                performance_spec=NS(subject="x (tall)"),
            )
        ]
        result = NS(
            storyboard=NS(all_shots=shots),
            script=NS(logline="l", scenes=[NS(order=0)]),
            brief=NS(target_duration_sec=target),
            cast=[],
            acts=[],
        )
        return metrics_mod.compute(result)

    on = next(m for m in fake(20, 20)["metrics"] if m.key == "duration_adherence")
    off = next(m for m in fake(2, 20)["metrics"] if m.key == "duration_adherence")
    assert on.score == 1.0
    assert off.score < 0.2
