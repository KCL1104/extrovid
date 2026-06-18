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
    # Persisted VisualBrief dump (style/mood/palette/lighting/camera/negative rules) —
    # the art direction that feeds storyboard planning and final video prompts.
    visual_brief: dict | None = Field(default=None, sa_column=Column(JSON))
    # set when an upstream artifact changed after this set was planned
    stale: bool = Field(default=False)


class LookFrame(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    # nullable: shot keyframes are LookFrames without a concept set
    concept_set_id: str | None = Field(
        default=None, foreign_key="visualconceptset.id", index=True
    )
    prompt: str
    source_model: str | None = "qwen-image"  # planned, not invoked in M1
    image_asset_id: str | None = None  # ALWAYS None this milestone
    tags: list = Field(default_factory=list, sa_column=Column(JSON))
    promoted_as: str = Field(default=PromotedAs.NONE.value)
    selected: bool = False
    # Qwen-Image-Edit refine lineage: the frame this one was refined from.
    parent_frame_id: str | None = None
    # Keyframe quality gate: the AI verdict on a shot keyframe (identity/composition/view)
    # so it can be approved or revised BEFORE any video budget is spent. ReviewResult dump.
    review: dict | None = Field(default=None, sa_column=Column(JSON))
    score: float | None = None
