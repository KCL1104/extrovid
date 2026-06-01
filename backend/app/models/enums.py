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
    STORYBOARDED = "storyboarded"


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


# Milestone 1 only plans these two models (Phase 1 scope per the spec).
PLANNABLE_MODELS_M1 = frozenset({PreferredModel.T2V, PreferredModel.I2V})

# Storyboard global shot-count bounds (spec: a 15-30s video from 5-10 shots).
MIN_SHOTS = 5
MAX_SHOTS = 10

# Concept-set candidate-frame bounds (spec: 4-up or 8-up concept sets).
MIN_CONCEPT_FRAMES = 4
MAX_CONCEPT_FRAMES = 8
