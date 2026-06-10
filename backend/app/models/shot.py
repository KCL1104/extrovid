"""Shot table."""

import uuid

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
    # physical camera setup index — shots sharing a camera_id are the same setup
    camera_id: int = Field(default=0)
    # keyframe contract: planned opening/closing snapshots + the motion between them
    first_frame_desc: str | None = None
    last_frame_desc: str | None = None
    motion_desc: str | None = None
    variation_type: str = Field(default="small")  # small | medium | large
    # the generated keyframe image (a LookFrame) used as this shot's i2v/r2v seed
    keyframe_frame_id: str | None = Field(default=None, foreign_key="lookframe.id")
