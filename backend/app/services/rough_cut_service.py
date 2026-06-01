"""Assemble selected shot versions into one polished rough-cut video.

Per shot (storyboard order) pick the selected ShotVersion, else any with a generated video.
Real mode downloads the clips and renders with ffmpeg (bundled via imageio-ffmpeg):
  - transitions: xfade (video) + acrossfade (audio) per each shot's `transition` field
  - sound: keep each clip's own audio + a synthesized low ambient bed mixed under
  - captions: burn the scene's narration/dialogue (from Scene.beats) as subtitles
The pipeline is best-effort and staged: if a stage fails it degrades gracefully, and the
whole thing falls back to a plain concat so a cut is always produced. Mock mode emits a
placeholder MP4. Result is stored and recorded as a TimelineSequence.
"""

import asyncio
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.asset import ImageAsset
from app.models.enums import ShotTransition
from app.models.generation import ShotVersion
from app.models.scene import Scene
from app.models.shot import Shot
from app.models.timeline import TimelineSequence
from app.providers.video_factory import MOCK_MP4, download_bytes
from app.services.asset_service import presigned_url, store_bytes

_CROSSFADE = 0.5  # seconds for dissolve/fade
_QUICKCUT = 0.12  # near-instant for cut/match_cut/none (uniform xfade mechanism)


@dataclass
class _Clip:
    data: bytes
    duration: float
    transition: str  # transition AFTER this clip (to the next)


@dataclass
class _Caption:
    text: str
    start: float
    end: float


def _t_for(transition: str) -> float:
    return (
        _CROSSFADE
        if transition in (ShotTransition.DISSOLVE.value, ShotTransition.FADE.value)
        else _QUICKCUT
    )


# --------------------------------------------------------------------------- #
# ffmpeg helpers (sync; run under asyncio.to_thread)
# --------------------------------------------------------------------------- #


def _ff() -> str:
    from imageio_ffmpeg import get_ffmpeg_exe

    return get_ffmpeg_exe()


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _probe(ff: str, path: str) -> tuple[int, int, bool, float]:
    """(width, height, has_audio, duration_sec) parsed from ffmpeg -i stderr."""
    res = subprocess.run([ff, "-i", path], capture_output=True, text=True)
    err = res.stderr
    w = h = 0
    has_audio = "Audio:" in err
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
    dur = 0.0
    d = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if d:
        dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return w, h, has_audio, dur


def _normalize(ff: str, src: str, dst: str, w: int, h: int, nominal: float) -> None:
    _, _, has_audio, _ = _probe(ff, src)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    )
    common = ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ar", "44100", "-ac", "2"]
    if has_audio:
        _run([ff, "-y", "-i", src, "-vf", vf, *common, dst])
    else:
        _run(
            [
                ff,
                "-y",
                "-i",
                src,
                "-f",
                "lavfi",
                "-t",
                f"{max(nominal, 0.5):.3f}",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-vf",
                vf,
                *common,
                "-shortest",
                dst,
            ]
        )


def _build_body(
    ff: str, norm_paths: list[str], durs: list[float], trans: list[str], dst: str
) -> None:
    n = len(norm_paths)
    inputs: list[str] = []
    for p in norm_paths:
        inputs += ["-i", p]
    if n == 1:
        _run([ff, "-y", *inputs, "-c:v", "libx264", "-c:a", "aac", dst])
        return

    vparts, aparts = [], []
    vlabel, alabel = "0:v", "0:a"
    running = durs[0]
    for k in range(n - 1):
        t = max(0.05, min(_t_for(trans[k]), durs[k] - 0.05, durs[k + 1] - 0.05))
        offset = max(0.0, running - t)
        nv, na = f"v{k + 1}", f"a{k + 1}"
        vparts.append(
            f"[{vlabel}][{k + 1}:v]xfade=transition=fade:duration={t:.3f}:offset={offset:.3f}[{nv}]"
        )
        aparts.append(f"[{alabel}][{k + 1}:a]acrossfade=d={t:.3f}[{na}]")
        vlabel, alabel = nv, na
        running = running + durs[k + 1] - t
    fc = ";".join(vparts + aparts)
    _run(
        [
            ff,
            "-y",
            *inputs,
            "-filter_complex",
            fc,
            "-map",
            f"[{vlabel}]",
            "-map",
            f"[{alabel}]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            dst,
        ]
    )


def _synth_bed(ff: str, duration: float, dst: str) -> None:
    # gentle low ambient pad (two detuned low sines + tremolo + lowpass, quiet)
    _run(
        [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=110:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=164.81:sample_rate=44100",
            "-filter_complex",
            "[0][1]amix=inputs=2,tremolo=f=0.12:d=0.5,lowpass=f=500,volume=0.10[a]",
            "-map",
            "[a]",
            "-t",
            f"{max(duration, 0.5):.3f}",
            dst,
        ]
    )


def _finalize(ff: str, body: str, srt: str | None, bed: str | None, dst: str) -> None:
    inputs = ["-i", body]
    if bed:
        inputs += ["-i", bed]
    vchain = (
        f"[0:v]subtitles={srt}:force_style='Alignment=2,FontSize=18,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,BorderStyle=1,Outline=2,Shadow=0,MarginV=40'[outv]"
        if srt
        else None
    )
    achain = "[0:a][1:a]amix=inputs=2:duration=first[outa]" if bed else None
    args = [ff, "-y", *inputs]
    if vchain and achain:
        args += ["-filter_complex", f"{vchain};{achain}", "-map", "[outv]", "-map", "[outa]"]
    elif vchain:
        args += ["-filter_complex", vchain, "-map", "[outv]", "-map", "0:a"]
    elif achain:
        args += ["-filter_complex", achain, "-map", "0:v", "-map", "[outa]"]
    else:
        args += ["-c", "copy"]
    if vchain or achain:
        args += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
    args.append(dst)
    _run(args)


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _plain_concat(ff: str, norm_paths: list[str], dst: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        lst = os.path.join(d, "list.txt")
        with open(lst, "w") as fh:
            fh.write("".join(f"file '{p}'\n" for p in norm_paths))
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", dst])


def render_rough_cut(clips: list[_Clip], captions: list[_Caption], want_music: bool) -> bytes:
    ff = _ff()
    with tempfile.TemporaryDirectory() as d:
        # write + normalize
        raw = []
        for i, c in enumerate(clips):
            p = os.path.join(d, f"raw{i}.mp4")
            with open(p, "wb") as fh:
                fh.write(c.data)
            raw.append(p)
        w, h, _, _ = _probe(ff, raw[0])
        w, h = (w or 1280), (h or 720)
        norm, durs = [], []
        for i, src in enumerate(raw):
            dst = os.path.join(d, f"n{i}.mp4")
            _normalize(ff, src, dst, w, h, clips[i].duration)
            norm.append(dst)
            durs.append(_probe(ff, dst)[3] or clips[i].duration)

        # body: transitions (fall back to plain concat on failure)
        body = os.path.join(d, "body.mp4")
        try:
            _build_body(ff, norm, durs, [c.transition for c in clips], body)
        except subprocess.CalledProcessError:
            _plain_concat(ff, norm, body)

        # captions (.srt) — recompute timeline from probed durs + transitions
        srt_path = None
        if captions:
            try:
                srt_path = os.path.join(d, "sub.srt")
                with open(srt_path, "w") as fh:
                    for j, cap in enumerate(captions, 1):
                        fh.write(
                            f"{j}\n{_srt_ts(cap.start)} --> {_srt_ts(cap.end)}\n{cap.text}\n\n"
                        )
            except OSError:
                srt_path = None

        # bed
        bed_path = None
        if want_music:
            try:
                bed_path = os.path.join(d, "bed.wav")
                _synth_bed(ff, _probe(ff, body)[3] or 1.0, bed_path)
            except subprocess.CalledProcessError:
                bed_path = None

        # finalize (subtitles + bed); degrade to body on failure
        out = os.path.join(d, "out.mp4")
        if srt_path or bed_path:
            try:
                _finalize(ff, body, srt_path, bed_path, out)
            except subprocess.CalledProcessError:
                out = body
        else:
            out = body
        with open(out, "rb") as fh:
            return fh.read()


# --------------------------------------------------------------------------- #
# orchestration (async)
# --------------------------------------------------------------------------- #


async def _chosen(session: AsyncSession, project_id: str) -> list[tuple[ShotVersion, Shot]]:
    shots = (
        (
            await session.execute(
                select(Shot).where(Shot.project_id == project_id).order_by(Shot.order)
            )
        )
        .scalars()
        .all()
    )
    out: list[tuple[ShotVersion, Shot]] = []
    for shot in shots:
        versions = (
            (
                await session.execute(
                    select(ShotVersion).where(
                        ShotVersion.shot_id == shot.id, ShotVersion.output_asset_id.is_not(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        if versions:
            out.append((next((v for v in versions if v.selected), versions[-1]), shot))
    return out


def _scene_text(beats: list) -> str:
    parts = []
    for b in beats or []:
        if isinstance(b, dict):
            txt = b.get("dialogue") or b.get("narration")
            if txt:
                parts.append(str(txt))
    return " ".join(parts).strip()


async def _captions(session: AsyncSession, project_id: str, chosen, durs, trans) -> list[_Caption]:
    scenes = (
        (await session.execute(select(Scene).where(Scene.project_id == project_id))).scalars().all()
    )
    text_by_order = {s.order: _scene_text(s.beats) for s in scenes}
    # per-clip start in the xfade-compressed final timeline
    starts = [0.0]
    for k in range(len(durs) - 1):
        t = max(0.05, min(_t_for(trans[k]), durs[k] - 0.05, durs[k + 1] - 0.05))
        starts.append(starts[k] + durs[k] - t)
    caps: list[_Caption] = []
    i = 0
    n = len(chosen)
    while i < n:
        order = chosen[i][1].scene_order
        j = i
        while j + 1 < n and chosen[j + 1][1].scene_order == order:
            j += 1
        text = text_by_order.get(order, "")
        if text:
            caps.append(_Caption(text=text[:200], start=starts[i], end=starts[j] + durs[j]))
        i = j + 1
    return caps


async def assemble_rough_cut(session: AsyncSession, project_id: str) -> TimelineSequence:
    chosen = await _chosen(session, project_id)
    if not chosen:
        raise LookupError("no generated shot videos to assemble")

    settings = get_settings()
    if settings.use_mock_video:
        data, use_mock, source_model = MOCK_MP4, True, "rough-cut:mock"
    else:
        clips: list[_Clip] = []
        for v, shot in chosen:
            asset = await session.get(ImageAsset, v.output_asset_id)
            blob = await download_bytes(presigned_url(asset.bucket_key))
            clips.append(_Clip(data=blob, duration=shot.duration_sec, transition=shot.transition))
        durs = [c.duration for c in clips]
        trans = [c.transition for c in clips]
        captions = await _captions(session, project_id, chosen, durs, trans)
        data = await asyncio.to_thread(render_rough_cut, clips, captions, True)
        use_mock, source_model = False, "rough-cut"

    asset = await store_bytes(
        session,
        project_id,
        data,
        "video/mp4",
        prompt="rough cut",
        source_model=source_model,
        use_mock=use_mock,
    )
    seq = TimelineSequence(
        project_id=project_id,
        output_asset_id=asset.id,
        shot_version_ids=[v.id for v, _ in chosen],
        status="ready",
    )
    session.add(seq)
    await session.commit()
    return seq


async def list_rough_cuts(session: AsyncSession, project_id: str) -> list[TimelineSequence]:
    return list(
        (
            await session.execute(
                select(TimelineSequence)
                .where(TimelineSequence.project_id == project_id)
                .order_by(TimelineSequence.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
