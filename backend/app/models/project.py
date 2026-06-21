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
    # content intent/format (length selector); None = not chosen -> tier-default structure
    format: str | None = Field(default=None)
    # review-gate budget (P3): max projected render cost the user approved for this project.
    # None = no budget set; generation is blocked when the plan's projected cost exceeds it.
    budget_usd: float | None = Field(default=None)
    # direction autonomy: "co" = pause at the review gate before spending (default);
    # "auto" = run straight through, review at the end. The budget ceiling still applies.
    autonomy: str = Field(default="co")
    created_at: datetime = Field(default_factory=_now)


class Brief(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    raw_prompt: str
    parsed: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # director Q&A answers — durable creative direction re-injected into every
    # downstream planning prompt (not consumed once by the brief and discarded)
    clarifications: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
