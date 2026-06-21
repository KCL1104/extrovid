"""Golden prompts — small, representative, stable. Change deliberately (they're the ruler).

Covers the cheap-to-run tiers: a short no-cast ad, a medium cast-driven story, a short
cast-driven trailer. LONG is intentionally omitted from the default set (slow + many scenes);
add one here when you want to measure chapter/act structure — the harness handles any duration.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Golden:
    id: str
    raw_prompt: str
    target_duration_sec: int
    expect_cast: bool  # should this brief yield named, recurring characters?


GOLDEN: list[Golden] = [
    Golden(
        "coffee-ad-20s",
        "a cozy 20-second ad for an artisan coffee brand, warm morning light in a small cafe",
        20,
        expect_cast=False,
    ),
    Golden(
        "founder-story-75s",
        "a 75-second brand story: a solo founder builds her ceramics studio from nothing, "
        "from empty room to first sale",
        75,
        expect_cast=True,
    ),
    Golden(
        "scifi-trailer-30s",
        "a 30-second teaser trailer for a sci-fi short: a lone astronaut wakes on an empty "
        "station and finds a message she does not remember leaving",
        30,
        expect_cast=True,
    ),
]
