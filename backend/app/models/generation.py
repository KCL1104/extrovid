"""RESERVED extension points — ShotVersion + GenerationJob.

Defined so the schema is future-proof (Phase 1+ video generation), but no API or logic
touches them in Milestone 1.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import JobStatus, ShotVersionStatus


class ShotVersion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shot_id: str = Field(foreign_key="shot.id", index=True)
    parent_version_id: str | None = Field(default=None, foreign_key="shotversion.id")
    model: str | None = None
    prompt: str | None = None
    input_assets: list = Field(default_factory=list, sa_column=Column(JSON))
    output_asset_id: str | None = None
    status: str = Field(default=ShotVersionStatus.DRAFT.value)
    score: float | None = None
    selected: bool = False


class GenerationJob(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    shot_version_id: str = Field(foreign_key="shotversion.id", index=True)
    provider: str | None = None
    model: str | None = None
    task_id: str | None = None
    status: str = Field(default=JobStatus.QUEUED.value)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    cost_usd: float = 0.0
