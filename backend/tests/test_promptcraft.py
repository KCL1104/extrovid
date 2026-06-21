"""Prompt composition — project memory (visual brief / style pack / character) injection."""

from app.models.memory import CharacterProfile, StylePack
from app.models.shot import Shot
from app.services.prompt_service import (
    compose_keyframe_prompt,
    compose_negative_prompt,
    compose_shot_prompt,
)

VISUAL_BRIEF = {
    "scene_order": 0,
    "visual_style": "modern cinematic",
    "mood": "warm and aspirational",
    "palette": ["#2b2b2b", "#d9a066"],
    "lighting": "soft golden-hour key light",
    "camera_language": "slow push-ins",
    "environment_notes": "minimal, uncluttered set",
    "negative_rules": ["no harsh shadows"],
}


def _shot() -> Shot:
    return Shot(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal the product",
        duration_sec=4,
        beat="hero moment",
        camera_spec={"shot_size": "CU", "angle": "low", "movement": "dolly-in"},
        performance_spec={"subject": "the watch", "action": "rotates slowly", "emotion": "calm"},
    )


def test_visual_brief_reaches_the_prompt():
    p = compose_shot_prompt(_shot(), visual_brief=VISUAL_BRIEF)
    assert "reveal the product" in p
    assert "CU low dolly-in" in p
    assert "modern cinematic" in p
    assert "soft golden-hour key light" in p
    assert "#2b2b2b" in p
    assert "minimal, uncluttered set" in p
    # negatives no longer ride inside the positive prompt — they are a real parameter
    assert "Avoid" not in p
    assert "no harsh shadows" in compose_negative_prompt(visual_brief=VISUAL_BRIEF)


def test_style_pack_and_character_injection():
    sp = StylePack(
        project_id="p",
        label="Brand",
        visual_style="film noir",
        lighting="hard rim light",
        negative_rules=["no logos other than the brand"],
    )
    ch = CharacterProfile(
        project_id="p",
        name="Mia",
        description="red coat, short black hair",
        wardrobe_rules=["always wears the red coat"],
        forbidden_changes=["never change her hair"],
    )
    p = compose_shot_prompt(
        _shot(),
        visual_brief=VISUAL_BRIEF,
        style_pack=sp,
        character=ch,
        has_reference_images=True,
    )
    assert p.startswith("The primary subject matches the reference portrait of Mia")
    assert "film noir" in p
    assert "hard rim light" in p  # style pack lighting wins over the brief's
    assert "featuring Mia: red coat, short black hair" in p
    assert "always wears the red coat" in p
    neg = compose_negative_prompt(visual_brief=VISUAL_BRIEF, style_pack=sp, character=ch)
    assert "never change her hair" in neg
    assert "no harsh shadows" in neg
    assert "no logos other than the brand" in neg


def test_negative_prompt_baseline_when_no_authored():
    # the always-on baseline means a silent planner still gets artifact protection
    neg = compose_negative_prompt()
    assert neg is not None
    assert "watermark" in neg


def test_authored_negatives_win_cap():
    # 8 authored rules fill the cap; the baseline is appended after, so it gets dropped
    authored = [f"rule-{i}" for i in range(8)]
    neg = compose_negative_prompt(visual_brief={"negative_rules": authored})
    for rule in authored:
        assert rule in neg
    assert "watermark" not in neg


def test_reference_line_without_character_is_generic():
    p = compose_shot_prompt(_shot(), has_reference_images=True)
    assert p.startswith("The main subject matches the reference image")


def test_default_style_and_lighting_when_brief_is_empty():
    p = compose_shot_prompt(_shot())  # bare shot — no brief
    assert "style: cinematic, shallow depth of field" in p
    assert "lighting: natural, motivated lighting" in p


def test_authored_style_and_lighting_suppress_the_defaults():
    p = compose_shot_prompt(_shot(), visual_brief=VISUAL_BRIEF)
    assert "style: modern cinematic" in p  # authored visual_style wins
    assert "shallow depth of field" not in p  # default style not appended
    assert "natural, motivated lighting" not in p  # brief has lighting → default suppressed


def test_reference_roles_add_guidance_clauses():
    # roles parallel to reference_asset_ids surface a "what to take" clause per ref
    p = compose_shot_prompt(_shot(), has_reference_images=True, reference_roles=["outfit", "prop"])
    assert "wardrobe matches the reference image" in p
    assert "object/prop matches the reference image" in p


def test_reference_roles_identity_and_unknown_are_silent():
    base = compose_shot_prompt(_shot(), has_reference_images=True)

    def p(roles):
        return compose_shot_prompt(_shot(), has_reference_images=True, reference_roles=roles)

    # identity is folded into the subject line; an unknown role is ignored — both byte-identical
    assert p(["identity"]) == base
    assert p(["bogus"]) == base
    assert base == compose_shot_prompt(_shot(), has_reference_images=True)  # default unchanged too


def test_bare_shot_still_produces_a_prompt():
    p = compose_shot_prompt(_shot())
    assert "reveal the product" in p
    assert "beat:" not in p  # internal planning metadata no longer leaks into the prompt
    assert p.endswith(".")  # well-formed join
    assert "Avoid" not in p


def test_framing_reaches_the_prompt():
    shot = _shot()
    shot.framing = "watch on right third, face dial toward camera, focus on the crown"
    p = compose_shot_prompt(shot)
    assert "framing: watch on right third, face dial toward camera" in p


def test_screen_direction_reaches_the_prompt():
    shot = _shot()
    shot.screen_direction = "moving left-to-right"
    p = compose_shot_prompt(shot)
    assert "screen direction: moving left-to-right" in p


def test_keyframe_seed_carries_facing_direction_even_with_first_frame_desc():
    """The i2v seed must encode facing/direction so the video doesn't default to facing camera."""
    shot = _shot()
    shot.first_frame_desc = "the figure at the airlock threshold, hand on the lever"
    shot.framing = "subject seen from behind, walking away from camera"
    shot.screen_direction = "moving away, deeper into the ship"
    p = compose_keyframe_prompt(shot, visual_brief=VISUAL_BRIEF)
    assert "the figure at the airlock threshold" in p  # planned snapshot still leads
    assert "framing: subject seen from behind, walking away" in p
    assert "screen direction: moving away" in p


def test_spoken_line_is_a_performance_cue_but_not_for_narrator():
    shot = _shot()
    shot.dialogue = "We did it."
    shot.speaker = "Maya"
    assert "speaking the line: We did it." in compose_shot_prompt(shot)
    shot.speaker = "narrator"  # voiceover is not a mouth-movement cue
    assert "speaking the line" not in compose_shot_prompt(shot)


def test_appearance_anchored_subject():
    """Cast-locked subjects carry visible appearance inline (ViMax appearance-not-name)."""
    ch = CharacterProfile(
        project_id="p",
        name="Mia",
        description="red coat, short black hair. Mid-30s.",
        wardrobe_rules=["always wears the red coat"],
    )
    shot = _shot()
    shot.performance_spec = {"subject": "Mia", "action": "walks toward the window"}
    p = compose_shot_prompt(shot, character=ch)
    assert "Mia (red coat, short black hair, always wears the red coat)" in p
    # the standalone character block stays too
    assert "featuring Mia" in p


def test_appearance_anchor_skips_unmatched_subject():
    ch = CharacterProfile(project_id="p", name="Mia", description="red coat")
    shot = _shot()  # subject is "the watch" — no name match, no rewrite
    p = compose_shot_prompt(shot, character=ch)
    assert "the watch rotates slowly" in p


def test_clarifications_reach_the_shot_prompt():
    answers = [
        {"question_id": "q1", "question": "Style?", "answer": "anime, melancholy ending"},
        {"question_id": "q2", "question": "Mood?", "answer": "   "},  # skipped
    ]
    p = compose_shot_prompt(_shot(), clarifications=answers)
    assert "Creative direction: anime, melancholy ending" in p
    assert compose_shot_prompt(_shot(), clarifications=[]) == compose_shot_prompt(_shot())
