"""Project CRUD endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.project import Project
from app.schemas.api import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create(
    data: ProjectCreate,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    # Admin (env token) has no user row → its projects are owned by the "admin" sentinel.
    owner_id = auth.user_id or "admin"
    return await project_service.create_project(session, owner_id, data)


@router.get("", response_model=list[ProjectRead])
async def list_all(
    auth: AuthCtx = Depends(current_auth), session: AsyncSession = Depends(get_session)
):
    projects = await project_service.list_projects(
        session, owner_id=auth.user_id, is_admin=auth.is_admin
    )
    stats = await project_service.stats_for(session, [p.id for p in projects])
    out = []
    for p in projects:
        read = ProjectRead.model_validate(p)
        read.stats = stats.get(p.id)
        out.append(read)
    return out


@router.get("/{project_id}", response_model=ProjectRead)
async def get_one(project: Project = Depends(get_owned_project)):
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update(
    data: ProjectUpdate,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    return await project_service.update_project(session, project, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    await project_service.delete_project(session, project)
