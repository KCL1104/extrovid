"""Keyframe contract + per-shot keyframe generation. Offline (mock LLM + images + video)."""

from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.services.prompt_service import compose_keyframe_prompt, compose_shot_prompt


async def _project(client):
    pid = (await client.post("/api/projects", json={"title": "KF"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, shots


async def test_storyboard_carries_the_keyframe_contract(client):
    _, shots = await _project(client)
    s = shots[0]
    assert s["first_frame_desc"]
    assert s["last_frame_desc"]
    assert s["motion_desc"]
    assert s["variation_type"] in ("small", "medium", "large")


def test_motion_desc_drives_the_video_prompt():
    shot = Shot(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal",
        duration_sec=4,
        beat="b",
        performance_spec={"subject": "the watch", "action": "rotates"},
        motion_desc="slow push-in as the watch (silver, black dial) rotates a quarter turn",
        last_frame_desc="the watch face fills the frame, dial readable",
    )
    p = compose_shot_prompt(shot)
    assert "slow push-in as the watch (silver, black dial)" in p
    assert "ending state: the watch face fills the frame" in p
    assert "the watch rotates" not in p  # motion_desc replaces the generic action line


def test_keyframe_prompt_is_a_static_snapshot():
    shot = Shot(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal",
        duration_sec=4,
        beat="b",
        camera_spec={"shot_size": "CU", "angle": "low"},
        performance_spec={"subject": "the watch", "action": "rotates"},
        first_frame_desc="the watch rests on dark slate, crown facing camera",
    )
    ch = CharacterProfile(project_id="p", name="Mia", description="red coat")
    p = compose_keyframe_prompt(
        shot, visual_brief={"visual_style": "noir", "lighting": "hard rim"}, character=ch
    )
    assert "the watch rests on dark slate" in p
    assert "the character is Mia: red coat" in p
    assert "camera: CU low" in p
    assert "no motion blur" in p


async def test_keyframe_endpoint_generates_and_routes(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    r = await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")
    assert r.status_code == 200
    frame = r.json()
    assert frame["image_asset_id"]

    shot = next(
        s for s in (await client.get(f"/api/projects/{pid}/storyboard")).json() if s["id"] == sid
    )
    assert shot["keyframe_frame_id"] == frame["id"]

    # generation prefers the keyframe as the first-frame seed
    v = (await client.post(f"/api/projects/{pid}/shots/{sid}/generate", json={})).json()
    assert "planned keyframe anchors composition" in v["routing_note"]

    # the keyframe is a LookFrame: the refine loop works on it for free
    r2 = await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/refine",
        json={"instruction": "warmer light"},
    )
    assert r2.status_code == 200


async def test_generate_all_keyframes_skips_existing(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")
    r = await client.post(f"/api/projects/{pid}/storyboard/keyframes")
    assert r.status_code == 200
    assert len(r.json()) == len(shots) - 1  # the one with a keyframe was skipped


async def test_explicit_first_frame_beats_keyframe(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    kf = (await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")).json()
    # an explicit first_frame_asset_id wins over the planned keyframe
    v = (
        await client.post(
            f"/api/projects/{pid}/shots/{sid}/generate",
            json={"first_frame_asset_id": kf["image_asset_id"]},
        )
    ).json()
    assert "planned keyframe" not in v["routing_note"]
    assert v["routing_note"].startswith("i2v")
