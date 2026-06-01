"""VisualConceptSet + LookFrame tables.

LookFrame.image_asset_id stays None in Milestone 1 (no image generation yet).
"""

import uuid

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import ConceptSetStatus, PromotedAs


class VisualConceptSet(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    scene_id: str | None = Field(default=None, foreign_key="scene.id", index=True)
    scene_order: int
    brief: str
    type: str
    status: str = Field(default=ConceptSetStatus.PLANNED.value)


class LookFrame(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    concept_set_id: str = Field(foreign_key="visualconceptset.id", index=True)
    prompt: str
    source_model: str | None = "qwen-image"  # planned, not invoked in M1
    image_asset_id: str | None = None  # ALWAYS None this milestone
    tags: list = Field(default_factory=list, sa_column=Column(JSON))
    promoted_as: str = Field(default=PromotedAs.NONE.value)
    selected: bool = False
