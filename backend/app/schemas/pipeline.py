"""Locked pipeline I/O schemas — the #1 deliverable of Milestone 1.

These plain Pydantic models are both the agent ``output_type`` contracts and the API
request/response bodies. They are deliberately separate from the SQLModel DB tables
(``app.models``) so ORM/session concerns never leak into agent output types.

Validation rules encode the spec's acceptance constraints:
- storyboard: 5-10 shots total, globally contiguous order, per-shot duration <= 15s
- concept set: 4-8 candidate look frames, at most one pre-selected
- shots may be planned to t2v/i2v/r2v (videoedit is execution-only)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    MAX_CONCEPT_FRAMES,
    MAX_SCENES,
    MAX_SHOTS_PER_SCENE,
    MAX_TOTAL_SHOTS,
    MIN_CONCEPT_FRAMES,
    MIN_TOTAL_SHOTS,
    PLANNABLE_MODELS,
    AspectRatio,
    ConceptSetStatus,
    ConceptSetType,
    PreferredModel,
    PromotedAs,
    ShotTransition,
)

# --------------------------------------------------------------------------- #
# Stage 0 — Brief
# --------------------------------------------------------------------------- #


class BriefInput(BaseModel):
    """User intent. ``raw_prompt`` is the only hard requirement; BriefAgent fills the rest."""

    raw_prompt: str = Field(..., min_length=1, description="Free text the user typed.")
    product: str | None = None
    story: str | None = None
    platform: str = Field(default="generic", description="tiktok / youtube / instagram / generic")
    target_duration_sec: int = Field(default=20, ge=5, le=600)
    aspect_ratio: AspectRatio = AspectRatio.R9_16
    style: str | None = None
    audience: str | None = None


# --------------------------------------------------------------------------- #
# Stage 1 — Script
# --------------------------------------------------------------------------- #


class SceneBeat(BaseModel):
    order: int = Field(..., ge=0)
    description: str = Field(..., min_length=1)
    narration: str | None = None
    dialogue: str | None = None


class SceneDraft(BaseModel):
    order: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    beats: list[SceneBeat] = Field(..., min_length=1)
    est_duration_sec: float = Field(..., gt=0)


class ScriptDraft(BaseModel):
    logline: str = Field(..., min_length=1)
    scenes: list[SceneDraft] = Field(..., min_length=1, max_length=MAX_SCENES)

    @model_validator(mode="after")
    def _scene_orders_unique(self) -> ScriptDraft:
        orders = [s.order for s in self.scenes]
        if len(set(orders)) != len(orders):
            raise ValueError("scene.order values must be unique")
        return self


# --------------------------------------------------------------------------- #
# Stage 1b — Cast (planned characters, extracted from the script)
# --------------------------------------------------------------------------- #


class CastMember(BaseModel):
    """A planned character. Features are renderable-only — they feed image/video models."""

    name: str = Field(..., min_length=1, description="Canonical name; group coreferences.")
    static_features: str = Field(
        ...,
        min_length=1,
        description=(
            "Visualizable, permanent traits only: gender, age range, build, concrete facial "
            "features (e.g. 'large eyes, a high nose bridge'), hairstyle, skin tone. NEVER "
            "personality, role, or relationships."
        ),
    )
    dynamic_features: str = Field(
        ...,
        min_length=1,
        description="Scene-spanning wardrobe/props with specific colors (e.g. 'worn red "
        "coat over a grey hoodie, silver pendant').",
    )


class CastList(BaseModel):
    characters: list[CastMember] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _names_unique(self) -> CastList:
        names = [c.name.strip().lower() for c in self.characters]
        if len(set(names)) != len(names):
            raise ValueError("cast member names must be unique (group coreferences)")
        return self


# --------------------------------------------------------------------------- #
# Stage 2 — Visual brief + concept set spec (per scene)
# --------------------------------------------------------------------------- #


class VisualBrief(BaseModel):
    scene_order: int = Field(..., ge=0)
    visual_style: str = Field(..., min_length=1)
    mood: str = Field(..., min_length=1)
    palette: list[str] = Field(..., min_length=1, description="Hex or named colors.")
    lighting: str = Field(..., min_length=1)
    camera_language: str = Field(..., min_length=1)
    character_notes: str | None = None
    environment_notes: str | None = None
    negative_rules: list[str] = Field(default_factory=list)
    axis_lock: bool = Field(
        default=False,
        description=(
            "When true, the scene holds the 180-degree line: shots keep a consistent screen "
            "direction so the spatial geometry never flips across cuts within the scene."
        ),
    )


class PlannedLookFrame(BaseModel):
    """A planned concept image (prompt only — no image is generated in Milestone 1).

    ``image_asset_id`` stays ``None`` this milestone; it becomes a real asset id once the
    Qwen-Image layer ships.
    """

    prompt: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    type: ConceptSetType
    promoted_as: PromotedAs = PromotedAs.NONE
    selected: bool = False
    image_asset_id: str | None = None


class VisualConceptSetSpec(BaseModel):
    scene_order: int = Field(..., ge=0)
    brief: str = Field(..., min_length=1, description="Short text brief that drove the set.")
    type: ConceptSetType
    status: ConceptSetStatus = ConceptSetStatus.PLANNED
    candidate_look_frames: list[PlannedLookFrame] = Field(
        ..., min_length=MIN_CONCEPT_FRAMES, max_length=MAX_CONCEPT_FRAMES
    )

    @model_validator(mode="after")
    def _at_most_one_selected(self) -> VisualConceptSetSpec:
        if sum(1 for f in self.candidate_look_frames if f.selected) > 1:
            raise ValueError("at most one look frame may be pre-selected")
        return self


class SceneVisualPlan(BaseModel):
    """VisualDevelopmentAgent output for a single scene: brief + concept set together."""

    visual_brief: VisualBrief
    concept_set: VisualConceptSetSpec

    @model_validator(mode="after")
    def _scene_orders_match(self) -> SceneVisualPlan:
        if self.visual_brief.scene_order != self.concept_set.scene_order:
            raise ValueError("visual_brief and concept_set must share the same scene_order")
        return self


# --------------------------------------------------------------------------- #
# Stage 3 — Storyboard (executable shot list)
# --------------------------------------------------------------------------- #


class CameraSpec(BaseModel):
    shot_size: str = Field(..., min_length=1, description="ECU/CU/MS/WS/EWS, etc.")
    angle: str = Field(..., min_length=1, description="eye-level/low/high/dutch, etc.")
    movement: str = Field(..., min_length=1, description="static/pan/tilt/dolly/handheld, etc.")
    lens: str | None = None


class PerformanceSpec(BaseModel):
    subject: str = Field(
        ...,
        min_length=1,
        description=(
            "WHO/WHAT performs, anchored by visible appearance, not a bare name: "
            "'Alice (short hair, green dress)' is correct; 'Alice' alone is not. "
            "Indicate the direction the subject is facing when it matters."
        ),
    )
    action: str = Field(
        ...,
        min_length=1,
        description=(
            "Concrete, observable, filmable action — no metaphors, no inner states "
            "(write 'turns away, avoiding eye contact', never 'feels ashamed')."
        ),
    )
    emotion: str | None = None


class ShotDTO(BaseModel):
    order: int = Field(..., ge=0, description="Global order across the whole storyboard.")
    scene_order: int = Field(..., ge=0)
    purpose: str = Field(..., min_length=1)
    duration_sec: float = Field(..., gt=0, le=15)
    beat: str = Field(..., min_length=1)
    camera_spec: CameraSpec
    performance_spec: PerformanceSpec
    preferred_model: PreferredModel = PreferredModel.T2V
    acceptance_rules: list[str] = Field(..., min_length=1)
    reference_look_frame_ids: list[str] = Field(default_factory=list)
    transition: ShotTransition = ShotTransition.CUT
    framing: str | None = Field(
        default=None,
        description=(
            "Blocking: where each visible subject sits in the frame, which direction "
            "they face, and what the focus is on "
            "(e.g. 'Maya on left third, facing right, focus on her hands')."
        ),
    )
    screen_direction: str | None = Field(
        default=None,
        description=(
            "Screen-direction continuity (the 180-degree line): which way the main subject "
            "faces or moves relative to the frame — e.g. 'moving left-to-right', 'facing "
            "camera-right'. Keep it consistent across shots in a scene unless a cut is "
            "motivated, so the geometry does not flip."
        ),
    )
    character_name: str | None = Field(
        default=None,
        description=(
            "When the shot features a cast member, their EXACT canonical name from the "
            "CAST list (enables the automatic cast lock). Null for shots without cast."
        ),
    )
    dialogue: str | None = Field(
        default=None,
        description=(
            "The ONE spoken line delivered during this shot, verbatim (no quotes, no stage "
            "directions). Null for silent shots. Put a beat's dialogue on the single shot "
            "that performs it."
        ),
    )
    speaker: str | None = Field(
        default=None,
        description=(
            "Who speaks the line — a cast member's canonical name, or 'narrator' for "
            "voiceover. Null when there is no dialogue."
        ),
    )
    first_frame_desc: str | None = Field(
        default=None,
        description=(
            "Pure static snapshot of the shot's OPENING image: composition, each visible "
            "subject's position and facing, lighting. NO ongoing actions — 'about to "
            "stand up' is unacceptable; write 'sitting on the chair, leaning slightly "
            "forward'."
        ),
    )
    last_frame_desc: str | None = Field(
        default=None,
        description=(
            "Pure static snapshot of the shot's CLOSING image, reflecting the final "
            "state after all camera and subject motion. Same snapshot rules."
        ),
    )
    motion_desc: str | None = Field(
        default=None,
        description=(
            "Everything that happens between the first and last frame, in professional "
            "camera terms (dolly, pan, push-in). Refer to characters by visible "
            "appearance, never bare name: 'Alice (short hair, green dress) is walking'."
        ),
    )
    variation_type: Literal["small", "medium", "large"] = Field(
        default="small",
        description=(
            "Intra-shot change: 'large' = composition/focus changes significantly (wide "
            "to close-up); 'medium' = subjects turn or reposition (back to front); "
            "'small' = expression or minor pose changes only."
        ),
    )
    camera_id: int = Field(
        default=0,
        ge=0,
        description=(
            "Index of the physical camera setup. Reuse an existing camera_id when this "
            "shot could be filmed from the same position; introduce a new id only if "
            "shot size, angle, and focus differ significantly. A camera that performs "
            "significant movement may not be reused afterward."
        ),
    )

    @field_validator("preferred_model")
    @classmethod
    def _plannable(cls, v: PreferredModel) -> PreferredModel:
        if v not in PLANNABLE_MODELS:
            allowed = sorted(m.value for m in PLANNABLE_MODELS)
            raise ValueError(f"The planner only routes to {allowed}; got {v.value}")
        return v


class StoryboardScene(BaseModel):
    scene_order: int = Field(..., ge=0)
    shots: list[ShotDTO] = Field(..., min_length=1, max_length=MAX_SHOTS_PER_SCENE)


class SceneShotPlan(BaseModel):
    """One scene's shot list — the per-scene planning unit (no planner sees more).

    Shot orders are LOCAL to the scene here; the orchestrator renumbers globally in
    Python (structural indices are never the LLM's job)."""

    scene_order: int = Field(..., ge=0)
    shots: list[ShotDTO] = Field(..., min_length=1, max_length=MAX_SHOTS_PER_SCENE)


class Storyboard(BaseModel):
    scenes: list[StoryboardScene] = Field(..., min_length=1)

    @property
    def all_shots(self) -> list[ShotDTO]:
        return [shot for scene in self.scenes for shot in scene.shots]

    @property
    def total_duration_sec(self) -> float:
        return sum(shot.duration_sec for shot in self.all_shots)

    @model_validator(mode="after")
    def _shot_count_and_contiguous_order(self) -> Storyboard:
        shots = self.all_shots
        n = len(shots)
        if not (MIN_TOTAL_SHOTS <= n <= MAX_TOTAL_SHOTS):
            raise ValueError(
                f"total shot count must be {MIN_TOTAL_SHOTS}..{MAX_TOTAL_SHOTS}, got {n}"
            )
        orders = sorted(shot.order for shot in shots)
        if orders != list(range(n)):
            raise ValueError(
                f"global shot.order must be 0..{n - 1} contiguous & unique, got {orders}"
            )
        return self


# --------------------------------------------------------------------------- #
# Aggregate result of the full pipeline
# --------------------------------------------------------------------------- #


class PipelineResult(BaseModel):
    brief: BriefInput
    script: ScriptDraft
    cast: list[CastMember] = Field(default_factory=list)
    visual_briefs: list[VisualBrief]
    concept_specs: list[VisualConceptSetSpec]
    storyboard: Storyboard
