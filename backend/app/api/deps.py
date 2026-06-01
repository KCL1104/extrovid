"""Shared FastAPI dependencies.

``get_owned_project`` is the per-request ownership gate: it loads the project and 404s
unless the caller owns it (or is admin). Attached as a router-level dependency on every
``/projects/{project_id}`` router so each project-scoped endpoint is access-checked once.
"""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.project import Project
from app.services import project_service


async def get_owned_project(
    project_id: str,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
) -> Project:
    project = await project_service.get_project(session, project_id)
    if project is None or (not auth.is_admin and project.owner_id != auth.user_id):
        # 404 (not 403) so project existence isn't leaked to non-owners.
        raise HTTPException(status_code=404, detail="project not found")
    return project
