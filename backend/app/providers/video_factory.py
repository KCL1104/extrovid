"""Video generation provider seam over the shared DashScope video-synthesis transport.

Both supported providers ride the SAME DashScope async submit->poll endpoint
(``dashscope_video_url``) with the SAME ``DASHSCOPE_API_KEY``; the ``VIDEO_PROVIDER`` flag only
selects which model id each abstract routing mode (t2v/i2v/r2v/videoedit) maps to:

- ``happyhorse`` (default) — HappyHorse (Alibaba; #1 on the Artificial Analysis Video Arena,
  native audio + 7-language lip-sync). t2v/i2v/r2v run on HappyHorse-1.1; video-edit has no 1.1
  on DashScope yet so it stays on happyhorse-1.0-video-edit.
- ``wan`` — Wan 2.7 (t2v/i2v/r2v/videoedit) everywhere.

``USE_MOCK_VIDEO`` swaps the whole transport for an instant deterministic mock so the
generation lifecycle is testable offline. The four public functions (``submit_video`` /
``submit_videoedit`` / ``poll_video`` / ``download_bytes``) keep stable signatures so
``generate_service`` and the reconciler are provider-agnostic; only ``SubmitResult.model``
reflects which model actually ran.
"""

import uuid
from dataclasses import dataclass

from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.core.http import request_with_retry

# Minimal MP4 header bytes (ftyp box) — not a playable video, just non-empty deterministic bytes.
MOCK_MP4 = bytes.fromhex("0000001c667479706d703432000000006d70343269736f6d") + b"\x00" * 32


@dataclass
class SubmitResult:
    task_id: str
    model: str


@dataclass
class PollResult:
    status: str  # PENDING | RUNNING | SUCCEEDED | FAILED
    video_url: str | None = None
    failure: str | None = None


def _resolve_video_model(settings: Settings, mode: str) -> str:
    """Map an abstract routing mode (t2v/i2v/r2v/videoedit) to the active provider's model id."""
    if settings.video_provider == "happyhorse":
        return {
            "t2v": settings.happyhorse_t2v_model,
            "i2v": settings.happyhorse_i2v_model,
            "r2v": settings.happyhorse_r2v_model,
            "videoedit": settings.happyhorse_videoedit_model,
        }[mode]
    return {
        "t2v": settings.wan_t2v_model,
        "i2v": settings.wan_i2v_model,
        "r2v": settings.wan_r2v_model,
        "videoedit": settings.wan_videoedit_model,
    }[mode]


def _build_r2v_media(refs: list[str], first_frame_url: str | None) -> list[dict]:
    """Reference-image media for r2v, reserving a slot for the first_frame seed.

    DashScope accepts at most 5 media items. The previous code appended the first_frame only
    ``if len(media) < 5``, so a full set of 5 references silently dropped the
    continuation/keyframe seed. Reserving the slot up front keeps the seed authoritative.
    """
    capacity = 5 - (1 if first_frame_url else 0)
    media: list[dict] = [{"type": "reference_image", "url": u} for u in (refs or [])[:capacity]]
    if first_frame_url:
        media.append({"type": "first_frame", "url": first_frame_url})
    return media


async def submit_video(
    prompt: str,
    *,
    ratio: str,
    duration: int,
    first_frame_url: str | None = None,
    reference_urls: list[str] | None = None,
    negative_prompt: str | None = None,
) -> SubmitResult:
    settings = get_settings()
    refs = reference_urls or []
    if refs:
        mode = "r2v"
    elif first_frame_url:
        mode = "i2v"
    else:
        mode = "t2v"
    model = _resolve_video_model(settings, mode)

    if settings.use_mock_video:
        return SubmitResult(task_id="mock-" + uuid.uuid4().hex, model=f"mock:{model}")

    return await _submit_dashscope(
        settings,
        model,
        mode,
        prompt,
        ratio=ratio,
        duration=duration,
        first_frame_url=first_frame_url,
        refs=refs,
        negative_prompt=negative_prompt,
    )


async def submit_videoedit(source_video_url: str, prompt: str) -> SubmitResult:
    """Instruction-based edit of an existing take (wan2.7-videoedit / happyhorse video-edit)."""
    settings = get_settings()
    model = _resolve_video_model(settings, "videoedit")
    if settings.use_mock_video:
        return SubmitResult(task_id="mock-" + uuid.uuid4().hex, model=f"mock:{model}")

    return await _submit_dashscope_edit(settings, model, source_video_url, prompt)


async def poll_video(task_id: str) -> PollResult:
    settings = get_settings()
    if settings.use_mock_video or task_id.startswith("mock-"):
        return PollResult(status="SUCCEEDED", video_url="mock://video")
    return await _poll_dashscope(settings, task_id)


# --- DashScope video-synthesis transport (async submit -> poll), shared by both providers -----


def _dashscope_async_headers(settings: Settings) -> dict:
    return {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }


async def _submit_dashscope(
    settings: Settings,
    model: str,
    mode: str,
    prompt: str,
    *,
    ratio: str,
    duration: int,
    first_frame_url: str | None,
    refs: list[str],
    negative_prompt: str | None,
) -> SubmitResult:
    await rate_limit.acquire("video")
    params = {
        "resolution": settings.video_resolution,
        "ratio": ratio,
        "duration": duration,
        "prompt_extend": True,
    }
    if negative_prompt:
        params["negative_prompt"] = negative_prompt
    if mode == "r2v":
        media = _build_r2v_media(refs, first_frame_url)
        body = {"model": model, "input": {"prompt": prompt, "media": media}, "parameters": params}
    elif mode == "i2v":
        body = {
            "model": model,
            "input": {"prompt": prompt, "media": [{"type": "first_frame", "url": first_frame_url}]},
            "parameters": {k: v for k, v in params.items() if k != "ratio"},
        }
    else:
        body = {"model": model, "input": {"prompt": prompt}, "parameters": params}
    resp = await request_with_retry(
        "POST",
        settings.dashscope_video_url,
        headers=_dashscope_async_headers(settings),
        json=body,
        timeout_sec=60,
    )
    resp.raise_for_status()
    return SubmitResult(task_id=resp.json()["output"]["task_id"], model=model)


async def _submit_dashscope_edit(
    settings: Settings, model: str, source_video_url: str, prompt: str
) -> SubmitResult:
    await rate_limit.acquire("video")
    body = {
        "model": model,
        "input": {"prompt": prompt, "media": [{"type": "video", "url": source_video_url}]},
        "parameters": {"resolution": settings.video_resolution, "prompt_extend": True},
    }
    resp = await request_with_retry(
        "POST",
        settings.dashscope_video_url,
        headers=_dashscope_async_headers(settings),
        json=body,
        timeout_sec=60,
    )
    resp.raise_for_status()
    return SubmitResult(task_id=resp.json()["output"]["task_id"], model=model)


async def _poll_dashscope(settings: Settings, task_id: str) -> PollResult:
    headers = {"Authorization": f"Bearer {settings.dashscope_api_key}"}
    resp = await request_with_retry(
        "GET", f"{settings.dashscope_task_url}/{task_id}", headers=headers, timeout_sec=60
    )
    resp.raise_for_status()
    payload = resp.json()
    out = payload.get("output", {})
    status = out.get("task_status", "RUNNING")
    if status == "SUCCEEDED":
        return PollResult(status="SUCCEEDED", video_url=out.get("video_url"))
    if status == "FAILED":
        return PollResult(
            status="FAILED", failure=str(out.get("message") or payload.get("message"))
        )
    return PollResult(status=status)


async def download_bytes(url: str) -> bytes:
    resp = await request_with_retry("GET", url, timeout_sec=180)
    resp.raise_for_status()
    return resp.content
