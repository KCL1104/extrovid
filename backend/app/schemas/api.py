"""API request/response models. Reuses the pipeline DTOs where possible."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    MAX_TARGET_DURATION_SEC,
    MIN_TARGET_DURATION_SEC,
    AnnotationIntent,
    AnnotationKind,
    AspectRatio,
    ProjectStatus,
    PromotedAs,
    ShotTransition,
    VideoFormat,
)
from app.schemas.pipeline import (
    CameraSpec,
    PerformanceSpec,
    ScriptDraft,
    VisualBrief,
    VisualConceptSetSpec,
)


class ProjectCreate(BaseModel):
    # title optional: when blank, the server auto-names it "Project N" for the owner.
    title: str | None = Field(default=None)
    aspect_ratio: AspectRatio = AspectRatio.R9_16
    target_duration_sec: int = Field(
        default=20, ge=MIN_TARGET_DURATION_SEC, le=MAX_TARGET_DURATION_SEC
    )
    format: VideoFormat | None = None  # content intent (length selector)


# --- auth ---


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    is_admin: bool
    daily_video_cap: int
    daily_image_cap: int
    created_at: datetime | None = None
    # Derived flags (not columns) — let the settings UI show the sign-in method.
    has_password: bool = False
    is_google: bool = False

    @classmethod
    def from_user(cls, user) -> "UserRead":
        return cls(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            daily_video_cap=user.daily_video_cap,
            daily_image_cap=user.daily_image_cap,
            created_at=user.created_at,
            has_password=user.password_hash is not None,
            is_google=user.google_sub is not None,
        )


class ChangePasswordRequest(BaseModel):
    # current_password omitted when a Google-only account sets its first password.
    current_password: str | None = None
    new_password: str


class AuthResponse(BaseModel):
    token: str
    user: UserRead


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    status: ProjectStatus | None = None
    aspect_ratio: AspectRatio | None = None
    target_duration_sec: int | None = Field(
        default=None, ge=MIN_TARGET_DURATION_SEC, le=MAX_TARGET_DURATION_SEC
    )
    format: VideoFormat | None = None


class ProjectStats(BaseModel):
    """Production progress counters shown on the dashboard / project header."""

    scenes: int = 0
    shots: int = 0
    rendered_shots: int = 0
    cuts: int = 0
    avg_score: float | None = None  # mean AI dailies score across scored takes (triage signal)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    owner_id: str
    status: str
    aspect_ratio: str
    target_duration_sec: int
    format: str | None = None
    created_at: datetime
    stats: ProjectStats | None = None


# --- clarifying questions (plan stage; stateless) ---


class ClarifyQuestion(BaseModel):
    """One multiple-choice director question about a genuinely ambiguous aspect."""

    id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    why: str = Field(..., min_length=1, description="What answering this unlocks.")
    options: list[str] = Field(..., min_length=2, max_length=4)
    allow_custom: bool = True


class ClarifyResult(BaseModel):
    needs_clarification: bool
    questions: list[ClarifyQuestion] = Field(default_factory=list, max_length=4)
    prompt_assessment: str = Field(
        ..., min_length=1, description="One line: what is clear / what is missing."
    )


class ClarifyAnswer(BaseModel):
    question_id: str
    question: str
    answer: str  # empty/whitespace answers are skipped when folding into the brief


class RunRequest(BaseModel):
    raw_prompt: str = Field(..., min_length=1)
    clarifications: list[ClarifyAnswer] = Field(default_factory=list)
    # explicit length/format selection (authoritative over brief-text inference)
    target_duration_sec: int | None = Field(
        default=None, ge=MIN_TARGET_DURATION_SEC, le=MAX_TARGET_DURATION_SEC
    )
    format: VideoFormat | None = None


class VisualPlansResponse(BaseModel):
    visual_briefs: list[VisualBrief]
    concept_specs: list[VisualConceptSetSpec]


class StoryboardRequest(BaseModel):
    script: ScriptDraft
    concept_specs: list[VisualConceptSetSpec] = []
    target_duration_sec: int = Field(
        default=20, ge=MIN_TARGET_DURATION_SEC, le=MAX_TARGET_DURATION_SEC
    )


# --- read models for stored planning artifacts ---


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    act_id: str | None = None  # LONG tier: the chapter this scene belongs to
    order: int
    title: str
    summary: str
    beats: list
    est_duration_sec: float
    stale: bool = False  # an upstream artifact changed after this was planned
    approved: bool = False  # signed off at the review gate
    locked: bool = False  # blocks targeted revision (revise/apply)


class LookFrameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prompt: str
    tags: list
    promoted_as: str
    selected: bool
    image_asset_id: str | None
    image_url: str | None = None  # presigned GET URL when an image has been generated
    parent_frame_id: str | None = None  # set when this frame was refined from another
    review: dict | None = None  # keyframe gate verdict (ReviewResult) — None until reviewed
    score: float | None = None  # keyframe gate score 0-10


class RefineFrameRequest(BaseModel):
    instruction: str = Field(..., min_length=1)


class PromoteRequest(BaseModel):
    target: PromotedAs
    name: str | None = None


class GenerateShotRequest(BaseModel):
    first_frame_asset_id: str | None = None
    reference_asset_ids: list[str] | None = None  # -> r2v consistency references
    character_id: str | None = None  # -> r2v using a CharacterProfile's reference frames
    # i2v continuation: seed this shot with the previous shot's last frame
    continue_from_previous: bool = False
    # best-of-N fan-out: submit N takes with the same direction; once all land, the
    # highest-scoring passing take is auto-selected (manual selection always wins)
    num_takes: int = Field(default=1, ge=1, le=4)


class ImportSourceRequest(BaseModel):
    """Long narrative source to import (script / novel chapter / transcript)."""

    text: str = Field(..., min_length=50)
    replace: bool = Field(default=False, description="Discard previous import progress.")


class ReviseRequest(BaseModel):
    """Targeted artifact revision. Targets must be real ids — never invented."""

    target: str = Field(
        ..., min_length=1, description="'scene:{id}' | 'visual_brief:{scene_id}' | 'shot:{id}'"
    )
    instruction: str = Field(..., min_length=1)
    # when true, return a non-destructive before/after proposal instead of committing
    dry_run: bool = Field(default=False)


class ReviseProposal(BaseModel):
    """A non-destructive revision proposal — the before/after diff for the review UI."""

    target: str
    kind: str
    before: dict
    after: dict
    instruction: str


class ApplyRevisionRequest(BaseModel):
    """Commit an accepted proposal's exact ``after`` (deterministic — no agent re-run)."""

    target: str = Field(..., min_length=1, description="'scene:{id}' | 'visual_brief:{scene_id}' | 'shot:{id}'")
    after: dict = Field(..., description="The proposed `after` object the user accepted.")


# --- review gate (P1) ---


class ApproveRequest(BaseModel):
    """Approve the whole plan (both lists omitted) or a subset of scenes/shots."""

    scene_ids: list[str] | None = None
    shot_ids: list[str] | None = None
    # optional spend ceiling set at sign-off (None leaves the existing budget untouched)
    budget_usd: float | None = Field(default=None, ge=0)


class LockRequest(BaseModel):
    locked: bool = True


class AnnotationCreate(BaseModel):
    target_kind: AnnotationKind
    target_id: str | None = None  # required for scene/shot/visual_brief; None for plan
    field: str | None = None
    intent: AnnotationIntent = AnnotationIntent.COMMENT
    text: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _anchor_needs_id(self) -> "AnnotationCreate":
        if self.target_kind != AnnotationKind.PLAN and not self.target_id:
            raise ValueError(f"{self.target_kind.value} annotations require a target_id")
        return self


class AnnotationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_kind: str
    target_id: str | None = None
    field: str | None = None
    intent: str
    text: str
    status: str
    created_at: datetime


class DirectorRequest(BaseModel):
    message: str = Field(..., min_length=1)


class DirectorResponse(BaseModel):
    reply: str
    actions: list[dict] = []  # tool calls the director made this turn
    state: dict = {}  # post-turn project snapshot


class BatchGenerateRequest(BaseModel):
    """Render a whole scene/project. With continuation, shots chain on upstream takes."""

    continue_from_previous: bool = False


class EditShotRequest(BaseModel):
    instruction: str = Field(..., min_length=1)


class CharacterRead(BaseModel):
    id: str
    name: str
    description: str | None = None
    reference_image_urls: list[str] = []
    wardrobe_rules: list[str] = []
    portrait_image_urls: dict[str, str] = {}  # {"front": url, "side": url, "back": url}


class StylePackRead(BaseModel):
    id: str
    label: str
    image_urls: list[str] = []


class ShotVersionRead(BaseModel):
    id: str
    shot_id: str
    parent_version_id: str | None = None
    model: str | None = None
    prompt: str | None = None  # the exact prompt that produced this take
    status: str
    selected: bool = False
    output_asset_id: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None  # extracted poster frame
    duration_sec: float | None = None  # probed real clip duration
    score: float | None = None  # ReviewAgent's 0-10 score
    review: dict | None = None  # {verdict, score, notes[], suggestions[]}
    routing_note: str | None = None  # why this take went to its Wan model
    job_id: str | None = None
    job_status: str | None = None
    failure_reason: str | None = None


class JobRead(BaseModel):
    """One generation job with its shot context — powers the project queue panel."""

    id: str
    status: str
    provider: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    cost_usd: float = 0.0
    shot_id: str
    shot_order: int
    shot_purpose: str
    version_id: str
    thumbnail_url: str | None = None


class ClipSpec(BaseModel):
    shot_version_id: str
    in_sec: float = Field(default=0.0, ge=0)
    out_sec: float | None = Field(default=None, gt=0)


class AssembleRequest(BaseModel):
    """Optional cut plan: ordered takes with trims, plus render options."""

    clips: list[ClipSpec] | None = None
    captions: bool = True
    music: bool = True
    voiceover: bool = True  # mix each shot's synthesized voiceover under the cut


class RoughCutRead(BaseModel):
    id: str
    status: str
    output_asset_id: str | None = None
    video_url: str | None = None
    shot_version_ids: list = []
    clips: list | None = None
    options: dict | None = None
    created_at: datetime | None = None
    published: bool = False
    published_id: str | None = None


class PublicVideoRead(BaseModel):
    id: str
    title: str
    aspect_ratio: str
    published_at: datetime
    stream_url: str


class ConceptSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scene_order: int
    brief: str
    type: str
    status: str
    visual_brief: dict | None = None  # the scene's persisted art direction
    look_frames: list[LookFrameRead] = []


class ShotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order: int
    scene_order: int
    purpose: str
    duration_sec: float
    beat: str
    camera_spec: dict
    performance_spec: dict
    preferred_model: str
    acceptance_rules: list
    reference_look_frame_ids: list
    transition: str
    extra_direction: str | None = None
    character_id: str | None = None
    framing: str | None = None
    screen_direction: str | None = None
    dialogue: str | None = None
    speaker: str | None = None
    vo_asset_id: str | None = None  # synthesized voiceover audio for this shot
    camera_id: int = 0
    first_frame_desc: str | None = None
    last_frame_desc: str | None = None
    motion_desc: str | None = None
    variation_type: str = "small"
    keyframe_frame_id: str | None = None
    last_keyframe_frame_id: str | None = None  # planned closing keyframe (continuity seed)
    keyframe_verdict: str | None = None  # keyframe gate verdict: "pass" | "revise" | None
    keyframe_score: float | None = None  # keyframe gate score 0-10
    stale: bool = False  # an upstream artifact changed after this was planned
    approved: bool = False  # signed off at the review gate
    locked: bool = False  # blocks targeted revision (revise/apply)


class ShotUpdate(BaseModel):
    """Partial shot edit (PATCH); only fields present in the request are applied."""

    purpose: str | None = Field(default=None, min_length=1)
    beat: str | None = Field(default=None, min_length=1)
    duration_sec: float | None = Field(default=None, gt=0, le=15)
    camera_spec: CameraSpec | None = None
    performance_spec: PerformanceSpec | None = None
    transition: ShotTransition | None = None
    acceptance_rules: list[str] | None = Field(default=None, min_length=1)
    extra_direction: str | None = None  # director's notes, fed verbatim into the prompt
    character_id: str | None = None  # cast lock: CharacterProfile of the same project
    framing: str | None = None  # blocking: subject positions + facing + focus
    screen_direction: str | None = None  # 180-degree line: subject facing/movement direction
    dialogue: str | None = None  # the one spoken line in this shot
    speaker: str | None = None  # who speaks it ('narrator' for VO)
    first_frame_desc: str | None = None  # planned opening snapshot (keyframe contract)
    last_frame_desc: str | None = None  # planned closing snapshot
    motion_desc: str | None = None  # the motion between the keyframes
    keyframe_frame_id: str | None = None  # point the shot at a different keyframe

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> "ShotUpdate":
        """Optional-to-omit, not optional-to-null: an explicit null on a non-nullable
        shot column would persist and break every later storyboard read."""
        nullable = {
            "extra_direction",
            "character_id",
            "framing",
            "screen_direction",
            "dialogue",
            "speaker",
            "first_frame_desc",
            "last_frame_desc",
            "motion_desc",
            "keyframe_frame_id",
        }
        for field in self.model_fields_set - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
