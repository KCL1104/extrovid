"""Audio: per-shot dialogue binding + captions + TTS voiceover. Offline (mock)."""

from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.services.audio_service import resolve_voice
from app.services.rough_cut_service import _captions


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
