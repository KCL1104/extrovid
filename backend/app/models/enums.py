"""Shared enums for the planning pipeline and DB entities.

These are the constrained vocabularies the schema validators depend on. ``PreferredModel``
keeps all four Wan model IDs as valid values for forward compatibility, but Milestone 1
validators only permit t2v/i2v (see ``app.schemas.pipeline.ShotDTO``).
"""

from enum import StrEnum


class PreferredModel(StrEnum):
    """Which Wan2.7 model a shot is routed to. r2v/videoedit reserved for later phases."""

    T2V = "wan2.7-t2v"
    I2V = "wan2.7-i2v"
    R2V = "wan2.7-r2v"
    VIDEOEDIT = "wan2.7-videoedit"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    SCRIPTED = "scripted"
    STORYBOARDED = "storyboarded"  # plan exists, awaiting human review (the review gate)
    APPROVED = "approved"  # plan signed off — generation is unlocked for gated tiers


class AnnotationKind(StrEnum):
    """What a review annotation is anchored to."""

    SCENE = "scene"
    SHOT = "shot"
    VISUAL_BRIEF = "visual_brief"
    PLAN = "plan"  # whole-plan note (no specific element)


class AnnotationIntent(StrEnum):
    COMMENT = "comment"  # a note for the human; no machine action
    CHANGE = "change"  # a revise instruction the agent can act on


class AnnotationStatus(StrEnum):
    OPEN = "open"
    APPLIED = "applied"  # a change annotation whose revision was committed
    RESOLVED = "resolved"  # archived (not deleted) — keeps the review trail


class AspectRatio(StrEnum):
    R16_9 = "16:9"
    R9_16 = "9:16"
    R1_1 = "1:1"
    R4_5 = "4:5"


class ConceptSetType(StrEnum):
    MOODBOARD = "moodboard"
    STYLE = "style"
    CHARACTER = "character"
    ENVIRONMENT = "environment"
    TITLE = "title"
    STORYBOARD_CARD = "storyboard_card"


class ConceptSetStatus(StrEnum):
    PLANNED = "planned"
    GENERATED = "generated"
    SELECTED = "selected"


class PromotedAs(StrEnum):
    NONE = "none"
    STYLE_PACK = "style_pack"
    CHARACTER_REF = "character_ref"
    FIRST_FRAME = "first_frame"
    STORYBOARD_CARD = "storyboard_card"


class ShotTransition(StrEnum):
    CUT = "cut"
    DISSOLVE = "dissolve"
    FADE = "fade"
    MATCH_CUT = "match_cut"
    NONE = "none"


class JobStatus(StrEnum):
    """Reserved for GenerationJob (async video jobs, later phases)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ShotVersionStatus(StrEnum):
    """Reserved for ShotVersion (video generation, later phases)."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# Milestone 1 only planned these two models (kept for reference/tests).
PLANNABLE_MODELS_M1 = frozenset({PreferredModel.T2V, PreferredModel.I2V})

# M2: r2v is plannable — the planner may route shots with recurring cast members to the
# highest-consistency mode instead of relying on execution-time upgrades. videoedit stays
# execution-only (it revises an existing take; there is nothing to plan).
PLANNABLE_MODELS = frozenset({PreferredModel.T2V, PreferredModel.I2V, PreferredModel.R2V})

# Per-scene storyboard bounds — no planner ever sees more than one scene's worth of
# shot design (the ViMax scaling move); scene COUNT scales with duration, scene size
# doesn't. Global totals are bounded loosely; contiguity is still enforced.
MIN_SHOTS = 5  # legacy single-call bound (kept for reference)
MAX_SHOTS = 10  # legacy single-call bound (kept for reference)
MIN_SHOTS_PER_SCENE = 1
MAX_SHOTS_PER_SCENE = 10
MIN_TOTAL_SHOTS = 1
MAX_TOTAL_SHOTS = 80
MAX_SCENES = 15
# a scene physically can't exceed this with <=10 shots of <=15s each
MAX_SCENE_DURATION_SEC = MAX_SHOTS_PER_SCENE * 15

# Concept-set candidate-frame bounds (spec: 4-up or 8-up concept sets).
MIN_CONCEPT_FRAMES = 4
MAX_CONCEPT_FRAMES = 8
