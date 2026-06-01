"""PublishedVideo: an opt-in public share of a finished rough cut (TimelineSequence).

One row per published sequence (``timeline_sequence_id`` unique). ``owner_id`` and ``title``
are denormalized so the public gallery can list without joining or leaking project internals.
The object stays private in the bucket; the public endpoint 302-redirects to a fresh
presigned URL per request.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class PublishedVideo(SQLModel, table=True):
    __tablename__ = "published_video"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    owner_id: str = Field(index=True)
    timeline_sequence_id: str = Field(foreign_key="timelinesequence.id", unique=True, index=True)
    output_asset_id: str  # ImageAsset id of the assembled video/mp4
    title: str  # snapshot of the project title at publish time
    aspect_ratio: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
