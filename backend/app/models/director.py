"""DirectorTurn — the director chat history (flat text, ViMax-style).

Continuity across turns comes from the per-turn project snapshot, not transcript
replay; only user/assistant text is persisted.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class DirectorTurn(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=_now)
