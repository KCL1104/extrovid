"""Real-FFmpeg integration tier: probing, frame extraction, and rough-cut rendering.

Runs offline against the bundled imageio-ffmpeg binary — the only tests that exercise
the production render path (previously shipped blind).
"""

import subprocess

import pytest

from app.providers.video_factory import MOCK_MP4
from app.services import media_service
from app.services.rough_cut_service import _Caption, _Clip, render_rough_cut


def _make_clip(path: str, duration: float = 0.8, color: str = "red") -> bytes:
    from imageio_ffmpeg import get_ffmpeg_exe

    ff = get_ffmpeg_exe()
    subprocess.run(
        [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x240:d={duration}",
            "-f",
            "lavfi",
            "-t",
            f"{duration}",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            path,
        ],  # fmt: skip
        check=True,
        capture_output=True,
    )
    with open(path, "rb") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def clip_bytes(tmp_path_factory) -> bytes:
    d = tmp_path_factory.mktemp("clips")
    return _make_clip(str(d / "a.mp4"))


def test_probe_video(clip_bytes):
    info = media_service.probe_video(clip_bytes)
    assert info is not None
    assert info.width == 320 and info.height == 240
    assert info.has_audio
    assert 0.5 < info.duration_sec < 1.2


def test_probe_rejects_mock_bytes():
    assert media_service.probe_video(MOCK_MP4) is None


def test_extract_poster_is_jpeg(clip_bytes):
    poster = media_service.extract_poster(clip_bytes)
    assert poster is not None
    assert poster[:3] == b"\xff\xd8\xff"  # JPEG magic


def test_extract_last_frame(clip_bytes):
    frame = media_service.extract_last_frame(clip_bytes)
    assert frame is not None
    assert frame[:3] == b"\xff\xd8\xff"


def test_extract_from_mock_bytes_returns_none():
    assert media_service.extract_poster(MOCK_MP4) is None
    assert media_service.extract_last_frame(MOCK_MP4) is None


def test_render_rough_cut_concat_and_trim(tmp_path):
    a = _make_clip(str(tmp_path / "a.mp4"), duration=1.0, color="red")
    b = _make_clip(str(tmp_path / "b.mp4"), duration=1.0, color="blue")
    clips = [
        _Clip(data=a, duration=1.0, transition="cut"),
        # trim the second clip to its middle 0.5s
        _Clip(data=b, duration=0.5, transition="cut", in_sec=0.25, out_sec=0.75),
    ]
    out = render_rough_cut(clips, [], want_music=False)
    assert out
    info = media_service.probe_video(out)
    assert info is not None
    # ~1.0 + ~0.5 minus the ~0.12s quick-cut xfade overlap
    assert 1.0 < info.duration_sec < 1.7


def test_render_rough_cut_with_captions_and_bed(tmp_path):
    a = _make_clip(str(tmp_path / "a.mp4"), duration=1.0, color="green")
    b = _make_clip(str(tmp_path / "b.mp4"), duration=1.0, color="black")
    clips = [
        _Clip(data=a, duration=1.0, transition="dissolve"),
        _Clip(data=b, duration=1.0, transition="cut"),
    ]
    caps = [_Caption(text="hello world", start=0.0, end=1.2)]
    out = render_rough_cut(clips, caps, want_music=True)
    info = media_service.probe_video(out)
    assert info is not None and info.has_audio
    assert 1.0 < info.duration_sec < 2.2
