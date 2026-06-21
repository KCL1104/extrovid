"""Still-vs-motion render mode — a low-motion shot freezes its keyframe into a clip
instead of paying for a full video generation (offline: mock video → MOCK_MP4)."""

import pytest

from app.services import media_service

# 1x1 red PNG (smallest valid image ffmpeg can loop)
_RED_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc0f01f0005000180fe8a3ccc0000000049454e44ae426082"
)


async def _project_with_storyboard(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "Still"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_still_shot_renders_without_video_spend(client):
    pid, shot_ids = await _project_with_storyboard(client)
    sid = shot_ids[0]
    r = await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"render_mode": "still"})
    assert r.status_code == 200
    assert r.json()["render_mode"] == "still"

    v = (await client.post(f"/api/projects/{pid}/shots/{sid}/generate")).json()
    assert v["job_status"] == "succeeded"
    assert v["output_asset_id"]
    assert v["model"] == "ffmpeg:still"


async def test_invalid_render_mode_rejected(client):
    pid, shot_ids = await _project_with_storyboard(client)
    r = await client.patch(
        f"/api/projects/{pid}/shots/{shot_ids[0]}", json={"render_mode": "hologram"}
    )
    assert r.status_code == 422


async def test_projected_cost_excludes_stills_from_video(client):
    pid, shot_ids = await _project_with_storyboard(client)
    before = (await client.get(f"/api/projects/{pid}/plan/cost")).json()
    await client.patch(f"/api/projects/{pid}/shots/{shot_ids[0]}", json={"render_mode": "still"})
    after = (await client.get(f"/api/projects/{pid}/plan/cost")).json()

    assert after["stills"] == 1
    assert after["video_usd"] < before["video_usd"]  # one fewer video render
    assert after["image_usd"] == before["image_usd"]  # the still still needs its keyframe


def test_still_to_clip_produces_a_real_clip():
    out = media_service.still_to_clip(_RED_PNG, 1.0)
    if out is None:
        pytest.skip("ffmpeg not available in this environment")
    info = media_service.probe_video(out)
    assert info is not None
    assert 0.5 <= info.duration_sec <= 2.0  # ~1s freeze clip
