"""Rough-cut assembly tests — offline (USE_MOCK_VIDEO: placeholder assemble, no ffmpeg)."""


async def _project_with_shots(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "Cut"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_rough_cut_requires_generated_videos(client):
    pid, _ = await _project_with_shots(client)
    r = await client.post(f"/api/projects/{pid}/rough-cut")
    # precise dependency report instead of a generic 400
    assert r.status_code == 422
    assert "finished takes" in str(r.json()["detail"]["missing"])


async def test_assemble_rough_cut(client):
    pid, shot_ids = await _project_with_shots(client)
    for sid in shot_ids[:2]:
        await client.post(f"/api/projects/{pid}/shots/{sid}/generate")

    r = await client.post(f"/api/projects/{pid}/rough-cut")
    assert r.status_code == 200
    cut = r.json()
    assert cut["status"] == "ready"
    assert cut["output_asset_id"]
    assert cut["video_url"].startswith("mock://")
    assert len(cut["shot_version_ids"]) == 2

    listed = (await client.get(f"/api/projects/{pid}/rough-cut")).json()
    assert len(listed) == 1
    assert listed[0]["id"] == cut["id"]


async def test_select_version_then_assemble(client):
    pid, shot_ids = await _project_with_shots(client)
    sid = shot_ids[0]
    # two versions for the same shot
    await client.post(f"/api/projects/{pid}/shots/{sid}/generate")
    v2 = (await client.post(f"/api/projects/{pid}/shots/{sid}/generate")).json()
    sel = await client.post(f"/api/projects/{pid}/shots/{sid}/versions/{v2['id']}/select")
    assert sel.status_code == 200

    versions = (await client.get(f"/api/projects/{pid}/shots/{sid}/versions")).json()
    selected = [v for v in versions if v["id"] == v2["id"]]
    assert selected  # the chosen version exists

    cut = (await client.post(f"/api/projects/{pid}/rough-cut")).json()
    assert v2["id"] in cut["shot_version_ids"]  # selected version was used


async def test_delete_project_with_rough_cut(client):
    pid, shot_ids = await _project_with_shots(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    await client.post(f"/api/projects/{pid}/rough-cut")
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
