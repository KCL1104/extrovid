"""TimelineSequence: an assembled rough cut (ordered shot versions -> one exported video)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class TimelineSequence(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    output_asset_id: str | None = None  # the assembled video (ImageAsset, content_type video/mp4)
    shot_version_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "ready"  # ready | failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
