"""Prompt composition — project memory (visual brief / style pack / character) injection."""

from app.models.memory import CharacterProfile, StylePack
from app.models.shot import Shot
from app.services.prompt_service import compose_negative_prompt, compose_shot_prompt

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
    assert compose_negative_prompt(visual_brief=VISUAL_BRIEF) == "no harsh shadows"


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
    assert p.startswith("The main subject matches the reference image")
    assert "film noir" in p
    assert "hard rim light" in p  # style pack lighting wins over the brief's
    assert "featuring Mia: red coat, short black hair" in p
    assert "always wears the red coat" in p
    neg = compose_negative_prompt(visual_brief=VISUAL_BRIEF, style_pack=sp, character=ch)
    assert "never change her hair" in neg
    assert "no harsh shadows" in neg
    assert "no logos other than the brand" in neg


def test_bare_shot_still_produces_a_prompt():
    p = compose_shot_prompt(_shot())
    assert "reveal the product" in p
    assert "beat: hero moment" in p
    assert "Avoid" not in p


def test_framing_reaches_the_prompt():
    shot = _shot()
    shot.framing = "watch on right third, face dial toward camera, focus on the crown"
    p = compose_shot_prompt(shot)
    assert "framing: watch on right third, face dial toward camera" in p


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
