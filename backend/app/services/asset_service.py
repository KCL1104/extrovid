"""Persist generated media (images, videos) to object storage and mint read URLs.

Real path uploads to the Railway/Tigris S3 bucket and serves via presigned GET URLs.
Mock path keeps bytes in a process-local dict and returns a ``mock://`` URL. Whether a
given asset is mock vs real is decided per-asset (mock-store membership), so image and
video can independently be mocked or real.
"""

import asyncio
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.asset import ImageAsset
from app.models.concept import LookFrame
from app.providers.image_factory import ImageResult
from app.schemas.api import LookFrameRead

# process-local store for mock mode: bucket_key -> bytes
_MOCK_STORE: dict[str, bytes] = {}

_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
}


@lru_cache
def _s3_client():
    import boto3
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        region_name=s.s3_region,
        config=Config(s3={"addressing_style": "virtual"}),
    )


def _ext(content_type: str) -> str:
    return _EXT.get(content_type, ".bin")


async def store_bytes(
    session: AsyncSession,
    project_id: str,
    content: bytes,
    content_type: str,
    *,
    prompt: str,
    source_model: str,
    use_mock: bool,
    width: int | None = None,
    height: int | None = None,
    cost_usd: float = 0.0,
) -> ImageAsset:
    asset = ImageAsset(
        project_id=project_id,
        bucket_key="",  # set below
        source_model=source_model,
        prompt=prompt,
        width=width,
        height=height,
        content_type=content_type,
        cost_usd=cost_usd,
    )
    key = f"{project_id}/{asset.id}{_ext(content_type)}"
    asset.bucket_key = key

    if use_mock:
        _MOCK_STORE[key] = content
    else:
        client = _s3_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=get_settings().s3_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    session.add(asset)
    await session.flush()
    return asset


async def store_image(
    session: AsyncSession, project_id: str, result: ImageResult, prompt: str
) -> ImageAsset:
    from app.core.pricing import image_cost_usd

    mock = get_settings().use_mock_image
    return await store_bytes(
        session,
        project_id,
        result.content,
        result.content_type,
        prompt=prompt,
        source_model=result.source_model,
        use_mock=mock,
        width=result.width,
        height=result.height,
        cost_usd=0.0 if mock else image_cost_usd(result.source_model),
    )


def presigned_url(bucket_key: str) -> str:
    if bucket_key in _MOCK_STORE:
        return f"mock://{bucket_key}"
    settings = get_settings()
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": bucket_key},
        ExpiresIn=settings.presign_ttl_sec,
    )


async def load_bytes(asset: ImageAsset) -> bytes:
    """Fetch a stored asset's raw bytes (mock store or S3)."""
    if asset.bucket_key in _MOCK_STORE:
        return _MOCK_STORE[asset.bucket_key]
    client = _s3_client()
    obj = await asyncio.to_thread(
        client.get_object, Bucket=get_settings().s3_bucket, Key=asset.bucket_key
    )
    return await asyncio.to_thread(obj["Body"].read)


async def delete_objects(keys: list[str]) -> None:
    """Best-effort removal of stored objects (mock store + real bucket). Never raises."""
    real: list[str] = []
    for k in keys:
        if k in _MOCK_STORE:
            _MOCK_STORE.pop(k, None)
        elif k:
            real.append(k)
    if not real:
        return
    bucket = get_settings().s3_bucket

    def _delete() -> None:
        client = _s3_client()
        for k in real:
            try:
                client.delete_object(Bucket=bucket, Key=k)
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                pass

    await asyncio.to_thread(_delete)


async def asset_url(session: AsyncSession, asset_id: str | None) -> str | None:
    """Resolve an ImageAsset id to a presigned GET URL (or None)."""
    if not asset_id:
        return None
    asset = await session.get(ImageAsset, asset_id)
    return presigned_url(asset.bucket_key) if asset else None


async def frames_to_read(session: AsyncSession, frames: list[LookFrame]) -> list[LookFrameRead]:
    return [
        LookFrameRead(
            id=f.id,
            prompt=f.prompt,
            tags=f.tags,
            promoted_as=f.promoted_as,
            selected=f.selected,
            image_asset_id=f.image_asset_id,
            image_url=await asset_url(session, f.image_asset_id),
            parent_frame_id=f.parent_frame_id,
        )
        for f in frames
    ]
