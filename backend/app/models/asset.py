"""ImageAsset: a generated concept image persisted in object storage.

LookFrame.image_asset_id points at one of these (plain string id, no DB FK to keep
insert ordering simple). bucket_key is the object key; reads return a presigned URL.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ImageAsset(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    bucket_key: str  # object key in the S3 bucket (empty for mock/in-memory)
    source_model: str
    prompt: str
    width: int | None = None
    height: int | None = None
    content_type: str = "image/png"
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
