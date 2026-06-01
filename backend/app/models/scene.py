"""Scene table."""

import uuid

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
