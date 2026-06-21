"""Deterministic structural metrics on a planning PipelineResult.

No LLM, no network — pure functions over the planned scenes/shots/cast. Each metric is both
a human-readable value and a 0..1 score; the aggregate is a single 0-100 headline. These
catch real regressions (duration drift, per-scene camera resets, orphan cast names, bare-name
subjects) that the unit tests don't, because the tests run on canned mock output.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.agents.tiers import tier_for
from app.schemas.pipeline import PipelineResult, ShotDTO


@dataclass
class Metric:
    key: str
    score: float  # 0..1 (or None when not applicable to this prompt)
    value: str  # human-readable detail
    applicable: bool = True


def _frac(num: int, den: int) -> float:
    return num / den if den else 1.0


def _subject_anchored(shot: ShotDTO) -> bool:
    """ViMax rule: a subject is anchored by visible appearance, not a bare name.
    Heuristic — the subject text carries an appearance descriptor (a parenthetical or a comma)."""
    s = (shot.performance_spec.subject or "").strip()
    return "(" in s or "," in s


def _keyframe_contract(shot: ShotDTO) -> bool:
    return bool(shot.first_frame_desc and shot.last_frame_desc and shot.motion_desc)


def compute(result: PipelineResult) -> dict:
    """Return {tier, metrics: [Metric...], overall: 0-100, totals: {...}}."""
    shots = result.storyboard.all_shots
    scenes = result.script.scenes
    target = result.brief.target_duration_sec
    cast_names = {c.name.strip().lower() for c in result.cast}
    n_shots = len(shots)
    n_scenes = len(scenes)

    metrics: list[Metric] = []

    # 1. duration adherence — planned shot seconds vs the authoritative target
    total = sum(s.duration_sec for s in shots)
    dur_score = max(0.0, 1.0 - abs(total - target) / target) if target else 0.0
    metrics.append(
        Metric("duration_adherence", dur_score, f"{total:.0f}s planned vs {target}s target")
    )

    # 2. keyframe contract coverage — every shot has opening/closing/motion descriptions
    kc = sum(1 for s in shots if _keyframe_contract(s))
    metrics.append(
        Metric("keyframe_contract", _frac(kc, n_shots), f"{kc}/{n_shots} shots fully specified")
    )

    # 3. screen-direction continuity authoring
    sd = sum(1 for s in shots if (s.screen_direction or "").strip())
    metrics.append(Metric("screen_direction", _frac(sd, n_shots), f"{sd}/{n_shots} shots set"))

    # 4. subject anchoring — among CAST-featuring shots, is the subject appearance-anchored?
    # (a bare name on a person is the drift risk; an object/environment subject is fine.)
    cast_shots = [s for s in shots if s.character_name]
    if cast_shots:
        sa = sum(1 for s in cast_shots if _subject_anchored(s))
        metrics.append(
            Metric(
                "subject_anchored",
                _frac(sa, len(cast_shots)),
                f"{sa}/{len(cast_shots)} cast shots anchored",
            )
        )
    else:
        metrics.append(Metric("subject_anchored", 1.0, "no cast shots", applicable=False))

    # 5. camera_id continuity — the baton renumbers globally; a per-scene reset to 0 is the bug
    by_scene: dict[int, list[ShotDTO]] = defaultdict(list)
    for s in shots:
        by_scene[s.scene_order].append(s)
    ordered_scene_keys = sorted(by_scene)
    resets = sum(1 for k in ordered_scene_keys[1:] if min(sh.camera_id for sh in by_scene[k]) == 0)
    later = max(0, len(ordered_scene_keys) - 1)
    cam_score = 1.0 - _frac(resets, later) if later else 1.0
    distinct_cams = len({s.camera_id for s in shots})
    metrics.append(
        Metric(
            "camera_continuity", cam_score, f"{distinct_cams} setups, {resets} per-scene reset(s)"
        )
    )

    # 6. cast referential integrity — every referenced character name exists in the cast
    referenced = [s.character_name.strip().lower() for s in shots if s.character_name]
    orphans = sorted({n for n in referenced if n not in cast_names})
    if referenced:
        ri = _frac(sum(1 for n in referenced if n in cast_names), len(referenced))
        detail = f"{len(cast_names)} cast, {len(orphans)} orphan name(s)" + (
            f": {', '.join(orphans)}" if orphans else ""
        )
        metrics.append(Metric("cast_integrity", ri, detail))
    else:
        metrics.append(Metric("cast_integrity", 1.0, "no cast referenced", applicable=False))

    # 7. character reuse — recurring across scenes (threaded), not invented per-scene
    scenes_of: dict[str, set[int]] = defaultdict(set)
    for s in shots:
        if s.character_name:
            scenes_of[s.character_name.strip().lower()].add(s.scene_order)
    distinct = len(scenes_of)
    recurring = sum(1 for v in scenes_of.values() if len(v) >= 2)
    if distinct and n_scenes > 1:
        metrics.append(
            Metric(
                "character_reuse",
                _frac(recurring, distinct),
                f"{recurring}/{distinct} recur across scenes",
            )
        )
    else:
        metrics.append(Metric("character_reuse", 1.0, "n/a", applicable=False))

    # 8. speaker integrity — every dialogue speaker is a cast member or the narrator
    spoken = [s for s in shots if (s.dialogue or "").strip()]
    if spoken:
        ok = sum(
            1 for s in spoken if (s.speaker or "").strip().lower() in cast_names | {"narrator"}
        )
        metrics.append(
            Metric(
                "speaker_integrity",
                _frac(ok, len(spoken)),
                f"{ok}/{len(spoken)} dialogue shots valid",
            )
        )
    else:
        metrics.append(Metric("speaker_integrity", 1.0, "no dialogue", applicable=False))

    applicable = [m for m in metrics if m.applicable]
    overall = (
        round(100 * sum(m.score for m in applicable) / len(applicable), 1) if applicable else 0.0
    )

    return {
        "tier": tier_for(target).name.lower(),
        "metrics": metrics,
        "overall": overall,
        "totals": {
            "scenes": n_scenes,
            "shots": n_shots,
            "acts": len(result.acts),
            "cast": len(result.cast),
            "planned_sec": round(total, 1),
            "target_sec": target,
        },
    }
