"""FFmpeg media utilities: probe metadata, extract poster / last frames.

Built on the same bundled binary as the rough-cut renderer (imageio-ffmpeg; the Docker
image pins a static ffmpeg + ffprobe via IMAGEIO_FFMPEG_EXE). Everything here is
best-effort and synchronous — callers wrap in ``asyncio.to_thread`` and treat ``None``
as "could not extract" (e.g. the mock MP4 placeholder is not decodable).

These helpers power the AI-native production loop:
- poster frames -> storyboard/queue thumbnails + ReviewAgent vision input
- last-frame extraction -> shot-to-shot continuation (previous take's final frame
  becomes the next shot's i2v first frame)
- probing -> real clip durations on ShotVersion (timeline math, review facts)
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

_FRAME_TIMEOUT = 60  # seconds per ffmpeg invocation; these are tiny clips


@dataclass
class MediaInfo:
    duration_sec: float | None
    width: int | None
    height: int | None
    has_audio: bool


def _ffmpeg() -> str:
    from imageio_ffmpeg import get_ffmpeg_exe  # respects IMAGEIO_FFMPEG_EXE

    return get_ffmpeg_exe()


def _ffprobe() -> str | None:
    """A real ffprobe when available (Docker image ships one); None otherwise."""
    candidate = os.environ.get("FFPROBE_EXE") or shutil.which("ffprobe")
    return candidate


def _probe_with_ffprobe(probe: str, path: str) -> MediaInfo:
    res = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=_FRAME_TIMEOUT,
        check=True,
    )
    data = json.loads(res.stdout)
    duration = None
    fmt = data.get("format") or {}
    if fmt.get("duration"):
        duration = float(fmt["duration"])
    width = height = None
    has_audio = False
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and width is None:
            width, height = stream.get("width"), stream.get("height")
        if stream.get("codec_type") == "audio":
            has_audio = True
    return MediaInfo(duration_sec=duration, width=width, height=height, has_audio=has_audio)


def _probe_with_ffmpeg(ff: str, path: str) -> MediaInfo:
    """Fallback: parse `ffmpeg -i` stderr (no ffprobe in the imageio-ffmpeg wheel)."""
    res = subprocess.run([ff, "-i", path], capture_output=True, text=True, timeout=_FRAME_TIMEOUT)
    err = res.stderr
    width = height = None
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    if m:
        width, height = int(m.group(1)), int(m.group(2))
    duration = None
    d = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if d:
        duration = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return MediaInfo(duration_sec=duration, width=width, height=height, has_audio="Audio:" in err)


def probe_video(data: bytes) -> MediaInfo | None:
    """Structured metadata for a video blob, or None when it is not decodable."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
            fh.write(data)
            path = fh.name
        try:
            probe = _ffprobe()
            info = (
                _probe_with_ffprobe(probe, path) if probe else _probe_with_ffmpeg(_ffmpeg(), path)
            )
            return info if info.duration_sec or info.width else None
        finally:
            os.unlink(path)
    except Exception:  # noqa: BLE001 - best-effort: undecodable/mock input
        return None


def _extract(args_builder, data: bytes) -> bytes | None:
    try:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.mp4")
            dst = os.path.join(d, "out.jpg")
            with open(src, "wb") as fh:
                fh.write(data)
            subprocess.run(
                args_builder(_ffmpeg(), src, dst),
                check=True,
                capture_output=True,
                timeout=_FRAME_TIMEOUT,
            )
            with open(dst, "rb") as fh:
                return fh.read()
    except Exception:  # noqa: BLE001 - best-effort: undecodable/mock input
        return None


def extract_poster(data: bytes, *, width: int = 480) -> bytes | None:
    """A JPEG poster frame from near the start of the clip (thumbnails, review vision)."""

    def args(ff: str, src: str, dst: str) -> list[str]:
        return [
            ff, "-y", "-ss", "0.25", "-i", src,
            "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", dst,
        ]  # fmt: skip

    return _extract(args, data) or _extract(
        # very short clips: retry from the first frame
        lambda ff, src, dst: [ff, "-y", "-i", src, "-frames:v", "1", "-q:v", "3", dst],
        data,
    )


def extract_last_frame(data: bytes) -> bytes | None:
    """The final frame at full resolution — the continuation seed for the next shot."""

    def args(ff: str, src: str, dst: str) -> list[str]:
        return [ff, "-y", "-sseof", "-0.3", "-i", src, "-frames:v", "1", "-q:v", "2", dst]

    out = _extract(args, data)
    if out:
        return out
    # -sseof can land past the end on sub-second clips; decode every frame into the same
    # output file (-update 1) so the last decoded frame is what survives
    return _extract(
        lambda ff, src, dst: [ff, "-y", "-i", src, "-q:v", "2", "-update", "1", dst],
        data,
    )
