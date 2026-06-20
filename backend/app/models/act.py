"""Act / Chapter table — the LONG-tier structure above scenes (P3b).

An act groups a contiguous run of scenes into a reviewable chapter with its own hook and an
open loop carried into the next act. Short/medium projects have no acts (Scene.act_id stays
None); only long-form planning emits them.
"""

import uuid

from sqlmodel import Field, SQLModel


class Act(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    order: int
    title: str
    hook: str = ""
    open_loop: str = ""
    summary: str = ""
