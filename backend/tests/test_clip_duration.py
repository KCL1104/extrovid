"""Video clip-length clamp — locks the floor at 3s (HappyHorse rejects <3s) and ceil rounding.

Regression: a 2.5s planned shot was banker's-rounded to 2 and floored at 2, which HappyHorse
rejected on DashScope ("duration must be between 3 and 15 seconds, got 2").
"""

from app.services.generate_service import _clip_duration


def test_clip_duration_floor_is_three():
    assert _clip_duration(2.0) == 3  # HappyHorse minimum
    assert _clip_duration(2.5) == 3  # ceil, not banker's round-to-2
    assert _clip_duration(0.4) == 3


def test_clip_duration_ceils_within_range():
    assert _clip_duration(7.1) == 8
    assert _clip_duration(8.0) == 8


def test_clip_duration_caps_at_fifteen():
    assert _clip_duration(15.0) == 15
    assert _clip_duration(20.0) == 15
