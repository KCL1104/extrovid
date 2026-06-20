"""Scene table."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Scene(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    order: int
    title: str
    summary: str
    beats: list = Field(default_factory=list, sa_column=Column(JSON))  # list[SceneBeat] dumps
    est_duration_sec: float = 0.0
    # set when an upstream artifact changed after this row was planned
    stale: bool = Field(default=False)
    # review gate (P1): signed off by the human, and frozen against bulk regeneration
    approved: bool = Field(default=False)
    locked: bool = Field(default=False)
    approved_at: datetime | None = Field(default=None)
