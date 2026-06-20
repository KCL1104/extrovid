"""Length tiers — the parametric spine for short/medium/long video planning.

A video's ``Tier`` is derived in Python from ``target_duration_sec`` (no new user input).
The same linear pipeline serves every length; the tier only changes *guidance* injected into
the planning prompts — narrative structure, scene-count range, and average shot length (ASL).
The chapter/act layer for the long tier is a later phase (see
``docs/length-tiers-and-review-gate.md``); this module is the P0 scaffolding.

Boundaries (locked 2026-06-20): SHORT <= 90s, MEDIUM 91-300s, LONG > 300s.
"""

from __future__ import annotations

from enum import StrEnum


class Tier(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


# inclusive upper bounds (sec); anything above MEDIUM's bound is LONG
_SHORT_MAX_SEC = 90
_MEDIUM_MAX_SEC = 300


def tier_for(target_duration_sec: int | float | None) -> Tier:
    """Map a target duration to its planning tier. ``None``/0 falls back to SHORT."""
    sec = target_duration_sec or 0
    if sec <= _SHORT_MAX_SEC:
        return Tier.SHORT
    if sec <= _MEDIUM_MAX_SEC:
        return Tier.MEDIUM
    return Tier.LONG


# Average-shot-length guidance per tier (seconds). Shorter ASL = faster cutting.
ASL_BY_TIER: dict[Tier, float] = {
    Tier.SHORT: 2.5,
    Tier.MEDIUM: 3.5,
    Tier.LONG: 4.5,
}

# Soft scene-count range per tier (the script agent still scales with duration; this anchors it).
SCENE_RANGE_BY_TIER: dict[Tier, tuple[int, int]] = {
    Tier.SHORT: (1, 3),
    Tier.MEDIUM: (3, 6),
    Tier.LONG: (6, 12),
}

# Narrative structure handed to the scriptwriter per tier.
_STRUCTURE_BY_TIER: dict[Tier, str] = {
    Tier.SHORT: (
        "a single-arc HOOK -> BODY -> PAYOFF. Front-load the strongest visual; scene 0 opens "
        "with a 1-3 second hook that stops the scroll, then deliver one idea and land a clean "
        "payoff. Keep cuts fast."
    ),
    Tier.MEDIUM: (
        "a clear three-part arc — setup -> development -> resolution (or problem -> solution -> "
        "call-to-action). Carry ONE core message; every scene advances it. Open with a hook in "
        "the first scene."
    ),
    Tier.LONG: (
        "a multi-section narrative grouped into 3-5 acts/chapters, each roughly 60-120s with its "
        "own mini-hook, a planted open loop, and a hand-off into the next section. Vary pacing: "
        "a tight intro, room to breathe through the body, a decisive close. Avoid one flat arc."
    ),
}


def script_tier_block(tier: Tier, target_duration_sec: int | float) -> str:
    """Tier-specific structural guidance appended to the scriptwriter prompt."""
    lo, hi = SCENE_RANGE_BY_TIER[tier]
    asl = ASL_BY_TIER[tier]
    return (
        f"\nFORMAT TIER: {tier.value} (~{target_duration_sec:g}s target).\n"
        f"Structure: write {_STRUCTURE_BY_TIER[tier]}\n"
        f"Aim for roughly {lo}-{hi} scenes and an average shot length around {asl:g}s "
        "(this sets how finely each scene will later be broken into shots)."
    )


# Format = the narrative STRUCTURE template, composed ON TOP of the tier's pacing spine.
# Tier controls length/pacing (ASL, scene count, hook); format controls the beat structure —
# so a 4-min explainer and a 4-min documentary derive to the same tier but read differently.
FORMAT_STRUCTURE: dict[str, str] = {
    "social": (
        "one idea only — a single stop-scroll hook in the first second, fast cuts, no "
        "exposition; end on the payoff or a loop."
    ),
    "ad": (
        "condensed hook -> value/demo -> explicit call-to-action; show the brand/product "
        "early and again at the close."
    ),
    "explainer": (
        "linear and chronological: Problem (5-10s) -> Solution (5-10s) -> How it works / "
        "key benefits (the bulk) -> a clear CTA (~10s). Budget narration near 2.5 words/sec."
    ),
    "youtube": (
        "a chaptered multi-scene piece with retention pacing — a strong cold open, signposted "
        "sections, recap/payoff beats, and varied energy so attention never flattens."
    ),
    "documentary": (
        "a non-linear, character/subject-driven arc; weave interview-style moments with B-roll "
        "and let the act/chapter structure carry the through-line."
    ),
}


def format_block(format: str | None) -> str:
    """Format-specific structure guidance appended to the scriptwriter prompt ("" when unset)."""
    if not format:
        return ""
    para = FORMAT_STRUCTURE.get(format)
    if not para:
        return ""
    return f"\nFORMAT ({format}): structure it as {para}"


def scene_shot_tier_block(
    tier: Tier, budget_sec: float, scene_order: int | None = None
) -> str:
    """Tier-specific pacing guidance for per-scene shot planning.

    The HOOK directive only fires for the very first scene of a SHORT piece, where the opening
    shot must earn the scroll-stop.
    """
    asl = ASL_BY_TIER[tier]
    approx = max(1, round(budget_sec / asl)) if budget_sec else 1
    block = (
        f"\nPACING ({tier.value}): aim for an average shot length around {asl:g}s "
        f"— roughly {approx} shot(s) for this {budget_sec:g}s scene; "
        "vary shot sizes (at least one wider establishing shot plus a closer insert)."
    )
    if tier is Tier.SHORT and scene_order == 0:
        block += (
            "\nHOOK: shot 0 is the stop-scroll hook — open on the single strongest, most "
            "legible image; no slow build-up."
        )
    return block
