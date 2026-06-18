"""Audio: per-shot dialogue binding + captions + TTS voiceover. Offline (mock)."""

import subprocess

from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.providers.audio_factory import MOCK_WAV
from app.services.audio_service import resolve_voice
from app.services.rough_cut_service import _captions, _Clip, _ff, _probe, render_rough_cut


def _shot(order: int, dialogue: str | None = None) -> Shot:
    return Shot(
        project_id="p",
        order=order,
        scene_order=0,
        purpose="x",
        duration_sec=4,
        beat="b",
        dialogue=dialogue,
    )


async def test_dialogue_binds_to_shots_through_planning(client):
    pid = (await client.post("/api/projects", json={"title": "Aud"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    spoken = [s for s in shots if s["dialogue"]]
    assert spoken  # at least one shot carries a spoken line
    for s in spoken:
        assert s["speaker"]  # a line always names a speaker


async def test_captions_prefer_per_shot_dialogue():
    chosen = [(None, _shot(0, "Hello there")), (None, _shot(1)), (None, _shot(2, "Goodbye"))]
    caps = await _captions(None, "p", chosen, [4.0, 4.0, 4.0], ["cut", "cut", "cut"])
    assert [c.text for c in caps] == ["Hello there", "Goodbye"]  # only shots with a line
    assert caps[1].start > caps[0].start  # the later shot's window starts later


async def test_dialogue_patchable_on_a_shot(client):
    pid = (await client.post("/api/projects", json={"title": "Aud2"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    sid = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]["id"]
    r = await client.patch(
        f"/api/projects/{pid}/shots/{sid}", json={"dialogue": "Cut!", "speaker": "narrator"}
    )
    assert r.status_code == 200
    assert r.json()["dialogue"] == "Cut!"
    assert r.json()["speaker"] == "narrator"


def test_resolve_voice_is_heuristic_and_stable():
    woman = CharacterProfile(project_id="p", name="Mia", description="a woman in her 30s")
    assert resolve_voice(woman)["voice"]  # seeds a voice from the description
    assert resolve_voice(None)["voice"]  # narrator / no-cast → a default voice
    locked = CharacterProfile(project_id="p", name="X", voice_lock={"voice": "Pinned"})
    assert resolve_voice(locked)["voice"] == "Pinned"  # an existing voice_lock wins


async def _project_with_dialogue(client) -> tuple[str, list[dict]]:
    pid = (await client.post("/api/projects", json={"title": "VO"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    return pid, (await client.get(f"/api/projects/{pid}/storyboard")).json()


async def test_voiceover_generation_sets_vo_asset(client):
    pid, shots = await _project_with_dialogue(client)
    sid = next(s["id"] for s in shots if s["dialogue"])
    r = await client.post(f"/api/projects/{pid}/shots/{sid}/voiceover")
    assert r.status_code == 200
    assert r.json()["vo_asset_id"]


async def test_voiceover_400_without_dialogue(client):
    pid, shots = await _project_with_dialogue(client)
    silent = next((s["id"] for s in shots if not s["dialogue"]), None)
    if silent is not None:
        r = await client.post(f"/api/projects/{pid}/shots/{silent}/voiceover")
        assert r.status_code == 400


async def test_voiceover_counts_as_audio_not_image(client):
    """The verified spend-leak fix: VO must bill against the audio cap, not image spend."""
    pid, shots = await _project_with_dialogue(client)
    sid = next(s["id"] for s in shots if s["dialogue"])
    before = (await client.get("/api/usage")).json()
    await client.post(f"/api/projects/{pid}/shots/{sid}/voiceover")
    after = (await client.get("/api/usage")).json()
    assert after["audio_today"] == before["audio_today"] + 1
    assert after["images_today"] == before["images_today"]  # not mislabeled as an image


def test_rough_cut_mixes_voiceover_through_ffmpeg(tmp_path):
    """Real ffmpeg coverage for the VO filtergraph — the mock path short-circuits, so the
    adelay/amix(normalize=0)/ducked-bed chain is otherwise untested."""
    ff = _ff()
    src = str(tmp_path / "clip.mp4")
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=0.4",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "0.4", "-c:v", "libx264", "-c:a", "aac", src,
        ],
        check=True,
        capture_output=True,
    )
    data = open(src, "rb").read()
    clips = [
        _Clip(data=data, duration=0.4, transition="cut", vo=MOCK_WAV),  # voiced shot
        _Clip(data=data, duration=0.4, transition="cut", vo=None),  # silent shot
    ]
    out = render_rough_cut(clips, captions=[], want_music=True)  # no subtitles → no libass dep
    op = str(tmp_path / "out.mp4")
    open(op, "wb").write(out)
    _, _, has_audio, dur = _probe(ff, op)
    assert has_audio and dur > 0 and len(out) > 1000  # a real encoded cut with a mixed track
