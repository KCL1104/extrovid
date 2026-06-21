"""Shot table."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import PreferredModel, ShotTransition


class Shot(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    scene_id: str | None = Field(default=None, foreign_key="scene.id", index=True)
    order: int  # global order across the storyboard
    scene_order: int
    purpose: str
    duration_sec: float
    beat: str
    camera_spec: dict = Field(default_factory=dict, sa_column=Column(JSON))
    performance_spec: dict = Field(default_factory=dict, sa_column=Column(JSON))
    preferred_model: str = Field(default=PreferredModel.T2V.value)
    acceptance_rules: list = Field(default_factory=list, sa_column=Column(JSON))
    reference_look_frame_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    transition: str = Field(default=ShotTransition.CUT.value)
    # per-shot detailed direction (PATCH /shots/{id}):
    extra_direction: str | None = None  # free-text director notes -> generation prompt verbatim
    character_id: str | None = Field(default=None, foreign_key="characterprofile.id")
    # blocking: subject frame positions + facing directions + focus (-> prompt + review)
    framing: str | None = None
    # screen-direction continuity (the 180-degree line): which way the subject faces/moves
    # relative to the frame — checked across shots so the geometry does not flip
    screen_direction: str | None = None
    # the one spoken line delivered in this shot + who says it ('narrator' for VO) — drives
    # captions, the performance prompt, and TTS voiceover
    dialogue: str | None = None
    speaker: str | None = None
    # the synthesized voiceover audio (an ImageAsset id, content_type audio/*) for this shot
    vo_asset_id: str | None = None
    # physical camera setup index — shots sharing a camera_id are the same setup
    camera_id: int = Field(default=0)
    # keyframe contract: planned opening/closing snapshots + the motion between them
    first_frame_desc: str | None = None
    last_frame_desc: str | None = None
    motion_desc: str | None = None
    variation_type: str = Field(default="small")  # small | medium | large
    # render mode: "video" = full i2v/t2v generation; "still" = freeze-frame clip from the
    # planned keyframe image (low-motion beats — establishing/text-card/held — at image cost)
    render_mode: str = Field(default="video")
    # the generated keyframe image (a LookFrame) used as this shot's i2v/r2v seed
    keyframe_frame_id: str | None = Field(default=None, foreign_key="lookframe.id")
    # the generated CLOSING keyframe (a LookFrame) — image-level continuity seed for the
    # NEXT shot, so chaining no longer depends on (or drifts through) rendered video
    last_keyframe_frame_id: str | None = Field(default=None, foreign_key="lookframe.id")
    # set when an upstream artifact (scene/brief) changed after this shot was planned
    stale: bool = Field(default=False)
    # review gate (P1): signed off by the human; `locked` blocks targeted revision (revise/apply)
    approved: bool = Field(default=False)
    locked: bool = Field(default=False)
    approved_at: datetime | None = Field(default=None)

    @property
    def suggest_still(self) -> bool:
        """Advisory hint shown at the review gate: a low-motion shot (no described motion)
        is a cheap candidate for a still render. The user confirms; nothing is forced."""
        m = (self.motion_desc or "").strip().lower()
        return self.render_mode == "video" and m in {
            "", "none", "static", "still", "locked", "no motion", "minimal",
        }  # fmt: skip
