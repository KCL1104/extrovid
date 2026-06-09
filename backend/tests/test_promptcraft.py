"""Prompt composition — project memory (visual brief / style pack / character) injection."""

from app.models.memory import CharacterProfile, StylePack
from app.models.shot import Shot
from app.services.prompt_service import compose_shot_prompt

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
    assert p.rstrip().endswith("Avoid: no harsh shadows.")


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
    assert "never change her hair" in p


def test_bare_shot_still_produces_a_prompt():
    p = compose_shot_prompt(_shot())
    assert "reveal the product" in p
    assert "beat: hero moment" in p
    assert "Avoid" not in p
