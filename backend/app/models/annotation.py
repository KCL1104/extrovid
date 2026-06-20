"""Annotation table — anchored review notes on the plan (P1 review gate).

An annotation pins a note to a scene, a shot, a scene's visual brief, or the whole plan,
optionally on a specific field. A ``change``-intent annotation carries an instruction the
revise agent can act on; its anchor (``target_kind`` + ``target_id``) is exactly the address
``revise_service`` dispatches on, so an annotation maps 1:1 onto a revision target.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.models.enums import AnnotationIntent, AnnotationStatus


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Annotation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    target_kind: str  # AnnotationKind: scene | shot | visual_brief | plan
    target_id: str | None = Field(default=None, index=True)  # scene/shot id; None for plan
    field: str | None = Field(default=None)  # the specific field the note is about
    intent: str = Field(default=AnnotationIntent.COMMENT.value)
    text: str
    status: str = Field(default=AnnotationStatus.OPEN.value)
    created_at: datetime = Field(default_factory=_utcnow)
