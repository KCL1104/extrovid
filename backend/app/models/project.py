"""Project + Brief tables."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import AspectRatio, ProjectStatus


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    # naive UTC to match TIMESTAMP WITHOUT TIME ZONE columns on Postgres
    return datetime.now(UTC).replace(tzinfo=None)


class Project(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    title: str
    owner_id: str  # single-user: the requester's id / email
    status: str = Field(default=ProjectStatus.DRAFT.value)
    aspect_ratio: str = Field(default=AspectRatio.R9_16.value)
    target_duration_sec: int = 20
    created_at: datetime = Field(default_factory=_now)


class Brief(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    raw_prompt: str
    parsed: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
