"""API request/response models. Reuses the pipeline DTOs where possible."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AspectRatio, ProjectStatus, PromotedAs
from app.schemas.pipeline import ScriptDraft, VisualBrief, VisualConceptSetSpec


class ProjectCreate(BaseModel):
    # title optional: when blank, the server auto-names it "Project N" for the owner.
    title: str | None = Field(default=None)
    aspect_ratio: AspectRatio = AspectRatio.R9_16
    target_duration_sec: int = Field(default=20, ge=5, le=120)


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


class AuthResponse(BaseModel):
    token: str
    user: UserRead


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    status: ProjectStatus | None = None
    aspect_ratio: AspectRatio | None = None
    target_duration_sec: int | None = Field(default=None, ge=5, le=120)


class ProjectStats(BaseModel):
    """Production progress counters shown on the dashboard / project header."""

    scenes: int = 0
    shots: int = 0
    rendered_shots: int = 0
    cuts: int = 0


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    owner_id: str
    status: str
    aspect_ratio: str
    target_duration_sec: int
    created_at: datetime
    stats: ProjectStats | None = None


class RunRequest(BaseModel):
    raw_prompt: str = Field(..., min_length=1)


class VisualPlansResponse(BaseModel):
    visual_briefs: list[VisualBrief]
    concept_specs: list[VisualConceptSetSpec]


class StoryboardRequest(BaseModel):
    script: ScriptDraft
    concept_specs: list[VisualConceptSetSpec] = []
    target_duration_sec: int = Field(default=20, ge=5, le=120)


# --- read models for stored planning artifacts ---


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order: int
    title: str
    summary: str
    beats: list
    est_duration_sec: float


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


class EditShotRequest(BaseModel):
    instruction: str = Field(..., min_length=1)


class CharacterRead(BaseModel):
    id: str
    name: str
    description: str | None = None
    reference_image_urls: list[str] = []


class StylePackRead(BaseModel):
    id: str
    label: str
    image_urls: list[str] = []


class ShotVersionRead(BaseModel):
    id: str
    shot_id: str
    parent_version_id: str | None = None
    model: str | None = None
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
