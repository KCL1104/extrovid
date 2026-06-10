"""Wan video generation: real DashScope async (submit -> poll) or an offline mock.

Gated by ``USE_MOCK_VIDEO``. Mock returns an instant task id and tiny placeholder MP4 bytes
so the whole generation lifecycle is testable offline and deterministically.
"""

import uuid
from dataclasses import dataclass

from app.core import rate_limit
from app.core.config import get_settings
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
        model, mode = settings.wan_r2v_model, "r2v"
    elif first_frame_url:
        model, mode = settings.wan_i2v_model, "i2v"
    else:
        model, mode = settings.wan_t2v_model, "t2v"

    if settings.use_mock_video:
        return SubmitResult(task_id="mock-" + uuid.uuid4().hex, model=f"mock:{model}")

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
        media = [{"type": "reference_image", "url": u} for u in refs[:5]]
        if first_frame_url and len(media) < 5:
            media.append({"type": "first_frame", "url": first_frame_url})
        body = {"model": model, "input": {"prompt": prompt, "media": media}, "parameters": params}
    elif mode == "i2v":
        body = {
            "model": model,
            "input": {"prompt": prompt, "media": [{"type": "first_frame", "url": first_frame_url}]},
            "parameters": {k: v for k, v in params.items() if k != "ratio"},
        }
    else:
        body = {"model": model, "input": {"prompt": prompt}, "parameters": params}
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    resp = await request_with_retry(
        "POST", settings.dashscope_video_url, headers=headers, json=body, timeout_sec=60
    )
    resp.raise_for_status()
    return SubmitResult(task_id=resp.json()["output"]["task_id"], model=model)


async def submit_videoedit(source_video_url: str, prompt: str) -> SubmitResult:
    """Instruction-based edit of an existing video (wan2.7-videoedit)."""
    settings = get_settings()
    model = settings.wan_videoedit_model
    if settings.use_mock_video:
        return SubmitResult(task_id="mock-" + uuid.uuid4().hex, model=f"mock:{model}")

    await rate_limit.acquire("video")
    body = {
        "model": model,
        "input": {"prompt": prompt, "media": [{"type": "video", "url": source_video_url}]},
        "parameters": {"resolution": settings.video_resolution, "prompt_extend": True},
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    resp = await request_with_retry(
        "POST", settings.dashscope_video_url, headers=headers, json=body, timeout_sec=60
    )
    resp.raise_for_status()
    return SubmitResult(task_id=resp.json()["output"]["task_id"], model=model)


async def poll_video(task_id: str) -> PollResult:
    settings = get_settings()
    if settings.use_mock_video or task_id.startswith("mock-"):
        return PollResult(status="SUCCEEDED", video_url="mock://video")

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
