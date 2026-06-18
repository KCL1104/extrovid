"""Audio: per-shot dialogue binding + caption windows. Offline (mock)."""

from app.models.shot import Shot
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
