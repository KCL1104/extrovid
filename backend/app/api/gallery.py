"""Gallery endpoints.

``router`` (gated, owner-only): publish / unpublish a finished rough cut.
``public_router`` (un-gated): list the public gallery + stream a published video via a
302 redirect to a freshly-minted presigned URL (objects stay private in the bucket).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.db import get_session
from app.models.asset import ImageAsset
from app.models.project import Project
from app.schemas.api import PublicVideoRead
from app.services import gallery_service
from app.services.asset_service import presigned_url

router = APIRouter(
    prefix="/projects/{project_id}", tags=["gallery"], dependencies=[Depends(get_owned_project)]
)
public_router = APIRouter(prefix="/gallery", tags=["gallery"])


# --- gated (owner) ---


@router.post("/rough-cut/{sequence_id}/publish", response_model=PublicVideoRead)
async def publish(
    sequence_id: str,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    try:
        pv = await gallery_service.publish(session, project, sequence_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return gallery_service.to_read(pv)


@router.delete("/rough-cut/{sequence_id}/publish", status_code=status.HTTP_204_NO_CONTENT)
async def unpublish(
    sequence_id: str,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_session),
):
    await gallery_service.unpublish(session, project, sequence_id)


# --- public (un-gated) ---


@public_router.get("", response_model=list[PublicVideoRead])
async def list_gallery(session: AsyncSession = Depends(get_session)):
    items = await gallery_service.list_public(session)
    return [gallery_service.to_read(pv) for pv in items]


@public_router.get("/{published_id}/video")
async def stream_gallery_video(published_id: str, session: AsyncSession = Depends(get_session)):
    pv = await gallery_service.get_public(session, published_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="not found")
    asset = await session.get(ImageAsset, pv.output_asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="not found")
    url = presigned_url(asset.bucket_key)
    if url.startswith("mock://"):
        raise HTTPException(status_code=404, detail="video unavailable")
    return RedirectResponse(url, status_code=302)
