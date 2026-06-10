"""SourceEvent — persisted long-source segmentation (resume = max(index))."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SourceEvent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    index: int
    description: str
    process_chain: list = Field(default_factory=list, sa_column=Column(JSON))
    is_last: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)
