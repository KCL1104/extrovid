"""Project CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.api import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


async def _get_or_404(session: AsyncSession, project_id: str):
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create(data: ProjectCreate, session: AsyncSession = Depends(get_session)):
    return await project_service.create_project(session, data)


@router.get("", response_model=list[ProjectRead])
async def list_all(session: AsyncSession = Depends(get_session)):
    return await project_service.list_projects(session)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_one(project_id: str, session: AsyncSession = Depends(get_session)):
    return await _get_or_404(session, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update(
    project_id: str, data: ProjectUpdate, session: AsyncSession = Depends(get_session)
):
    project = await _get_or_404(session, project_id)
    return await project_service.update_project(session, project, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(project_id: str, session: AsyncSession = Depends(get_session)):
    project = await _get_or_404(session, project_id)
    await project_service.delete_project(session, project)
