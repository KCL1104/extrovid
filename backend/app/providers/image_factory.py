"""Concept-image generation: real Qwen-Image (DashScope sync) or an offline mock.

Gated by ``USE_MOCK_IMAGE``. The mock returns a tiny valid PNG with the requested
dimensions — no network, deterministic — so the whole image flow is testable offline.
"""

import base64
from dataclasses import dataclass

from app.core import rate_limit
from app.core.config import get_settings
from app.core.http import request_with_retry
from app.models.enums import AspectRatio

# Pixel sizes keyed by aspect ratio. Accepted by both qwen-image and wan2.7-image-pro on the
# DashScope multimodal-generation endpoint (Wan also takes "1K"/"2K"/"4K", but pixel dims encode
# the aspect ratio the pipeline needs).
_SIZE_BY_ASPECT = {
    AspectRatio.R9_16.value: "928*1664",
    AspectRatio.R16_9.value: "1664*928",
    AspectRatio.R1_1.value: "1328*1328",
    AspectRatio.R4_5.value: "1140*1472",
}
_DEFAULT_SIZE = "1328*1328"

# 1x1 transparent PNG (smallest valid PNG) for mock output.
_MOCK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAADjm/uOAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def size_for_aspect(aspect_ratio: str) -> str:
    return _SIZE_BY_ASPECT.get(aspect_ratio, _DEFAULT_SIZE)


@dataclass
class ImageResult:
    content: bytes
    content_type: str
    width: int | None
    height: int | None
    source_model: str


def _parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        w, h = size.split("*")
        return int(w), int(h)
    except Exception:  # pragma: no cover - defensive
        return None, None


async def generate_image(
    prompt: str, size: str, negative_prompt: str | None = None
) -> ImageResult:
    settings = get_settings()
    if settings.use_mock_image:
        w, h = _parse_size(size)
        return ImageResult(
            content=_MOCK_PNG,
            content_type="image/png",
            width=w,
            height=h,
            source_model=f"mock:{settings.qwen_image_model}",
        )

    await rate_limit.acquire("image")
    params: dict = {"size": size, "n": 1, "prompt_extend": True, "watermark": False}
    if negative_prompt:
        params["negative_prompt"] = negative_prompt
    body = {
        "model": settings.qwen_image_model,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": params,
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    resp = await request_with_retry(
        "POST", settings.dashscope_image_url, headers=headers, json=body
    )
    resp.raise_for_status()
    data = resp.json()
    url = data["output"]["choices"][0]["message"]["content"][0]["image"]
    usage = data.get("usage", {})
    # Download immediately — DashScope image URLs expire after 24h.
    img = await request_with_retry("GET", url)
    img.raise_for_status()
    return ImageResult(
        content=img.content,
        content_type=img.headers.get("content-type", "image/png"),
        width=usage.get("width"),
        height=usage.get("height"),
        source_model=settings.qwen_image_model,
    )


async def edit_image(
    source_image_url: str, instruction: str, negative_prompt: str | None = None
) -> ImageResult:
    """Instruction-based refinement of an existing image (Qwen-Image-Edit).

    Closes the spec's previsual iterate loop: refine an approved look frame instead of
    regenerating concepts from scratch. ``source_image_url`` must be fetchable by the
    provider (we pass a presigned GET URL).
    """
    settings = get_settings()
    if settings.use_mock_image:
        return ImageResult(
            content=_MOCK_PNG,
            content_type="image/png",
            width=1,
            height=1,
            source_model=f"mock:{settings.qwen_image_edit_model}",
        )

    await rate_limit.acquire("image")
    edit_params: dict = {"n": 1, "watermark": False}
    if negative_prompt:
        edit_params["negative_prompt"] = negative_prompt
    body = {
        "model": settings.qwen_image_edit_model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"image": source_image_url}, {"text": instruction}],
                }
            ]
        },
        "parameters": edit_params,
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    resp = await request_with_retry(
        "POST", settings.dashscope_image_url, headers=headers, json=body
    )
    resp.raise_for_status()
    data = resp.json()
    url = data["output"]["choices"][0]["message"]["content"][0]["image"]
    usage = data.get("usage", {})
    img = await request_with_retry("GET", url)
    img.raise_for_status()
    return ImageResult(
        content=img.content,
        content_type=img.headers.get("content-type", "image/png"),
        width=usage.get("width"),
        height=usage.get("height"),
        source_model=settings.qwen_image_edit_model,
    )
