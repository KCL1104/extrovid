"""RESERVED extension points — CharacterProfile + StylePack (Phase 2 reusable memory).

Tables defined now so Phase 2 needs no disruptive migration. No API or logic in Milestone 1.
"""

import uuid

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class CharacterProfile(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    name: str
    description: str | None = None
    face_lock: dict = Field(default_factory=dict, sa_column=Column(JSON))
    voice_lock: dict = Field(default_factory=dict, sa_column=Column(JSON))
    wardrobe_rules: list = Field(default_factory=list, sa_column=Column(JSON))
    forbidden_changes: list = Field(default_factory=list, sa_column=Column(JSON))
    reference_look_frame_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    # canonical multi-view turnaround (image ASSET ids): {"front": id, "side": id, "back": id}
    # — the identity anchor prepended to every r2v reference set
    portrait_assets: dict = Field(default_factory=dict, sa_column=Column(JSON))


class StylePack(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    label: str
    visual_style: str | None = None
    lighting: str | None = None
    camera_language: str | None = None
    palette: list = Field(default_factory=list, sa_column=Column(JSON))
    negative_rules: list = Field(default_factory=list, sa_column=Column(JSON))
    look_frame_ids: list = Field(default_factory=list, sa_column=Column(JSON))
