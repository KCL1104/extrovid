"""videoedit (NL shot revision) tests — offline (mock). Edits a generated take into a new
take that preserves lineage and routes to the active provider's video-edit model
(happyhorse-1.0-video-edit by default; wan2.7-videoedit under VIDEO_PROVIDER=wan)."""


async def _shot_with_take(client):
    pid = (await client.post("/api/projects", json={"title": "Edit"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shot_id = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]["id"]
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_id}/generate")).json()
    return pid, shot_id, v


async def test_edit_creates_new_take_via_videoedit(client):
    pid, shot_id, v = await _shot_with_take(client)
    assert v["output_asset_id"]  # mock generate succeeded
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit",
        json={"instruction": "change the background to night"},
    )
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != v["id"]
    # provider-agnostic: wan2.7-videoedit / happyhorse-1.0-video-edit both contain "edit"
    assert "edit" in (new["model"] or "")

    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_id}/versions")).json()
    assert len(versions) == 2


async def test_edit_unknown_source_400(client):
    pid, shot_id, _ = await _shot_with_take(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/nope/edit",
        json={"instruction": "relight warmer"},
    )
    assert r.status_code == 400


async def test_edit_requires_instruction(client):
    pid, shot_id, v = await _shot_with_take(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit", json={"instruction": ""}
    )
    assert r.status_code == 422
