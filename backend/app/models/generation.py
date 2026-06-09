"""ShotVersion + GenerationJob — the video-generation execution entities.

Every generate / continue / edit creates a new ShotVersion (never overwrites). The
AI review layer writes ``score`` / ``review`` / ``status`` after ingest; ``routing_note``
records why the orchestrator picked a given Wan model for this take.
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
    # AI review (ReviewAgent): {"score", "verdict", "notes": [...], "suggestions": [...]}
    review: dict | None = Field(default=None, sa_column=Column(JSON))
    # Why this take was routed to its model (t2v/i2v/r2v/videoedit) — surfaced in the UI.
    routing_note: str | None = None
    # Poster frame extracted from the finished video (ImageAsset id) + probed duration.
    thumbnail_asset_id: str | None = None
    duration_sec: float | None = None
    # The request that produced this take (character/first-frame/refs/edit instruction) —
    # lets a failed job be retried with the exact same direction.
    gen_params: dict | None = Field(default=None, sa_column=Column(JSON))


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
