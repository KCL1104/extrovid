"""r2v consistency tests — offline (mock). Promote a concept frame to a character, then
generate a shot referencing it and confirm it routes to wan2.7-r2v."""


async def _project_with_images(client):
    pid = (await client.post("/api/projects", json={"title": "R2V"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]
    await client.post(f"/api/projects/{pid}/concept-sets/{cs['id']}/generate-images")
    frame = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["look_frames"][0]
    shot_ids = [s["id"] for s in (await client.get(f"/api/projects/{pid}/storyboard")).json()]
    return pid, frame, shot_ids


async def test_promote_character_then_listed_with_thumbnail(client):
    pid, frame, _ = await _project_with_images(client)
    r = await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/promote",
        json={"target": "character_ref", "name": "Hero"},
    )
    assert r.status_code == 200
    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    assert len(chars) == 1
    assert chars[0]["name"] == "Hero"
    assert len(chars[0]["reference_image_urls"]) >= 1


async def test_generate_shot_with_character_uses_r2v(client):
    pid, frame, shot_ids = await _project_with_images(client)
    await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/promote",
        json={"target": "character_ref", "name": "Hero"},
    )
    char_id = (await client.get(f"/api/projects/{pid}/characters")).json()[0]["id"]
    v = (
        await client.post(
            f"/api/projects/{pid}/shots/{shot_ids[0]}/generate", json={"character_id": char_id}
        )
    ).json()
    assert "r2v" in (v["model"] or "")


async def test_generate_shot_with_reference_assets_uses_r2v(client):
    pid, frame, shot_ids = await _project_with_images(client)
    v = (
        await client.post(
            f"/api/projects/{pid}/shots/{shot_ids[0]}/generate",
            json={"reference_asset_ids": [frame["image_asset_id"]]},
        )
    ).json()
    assert "r2v" in (v["model"] or "")


async def test_generate_shot_without_references_stays_t2v_or_i2v(client):
    pid, _, shot_ids = await _project_with_images(client)
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate", json={})).json()
    assert "r2v" not in (v["model"] or "")


async def test_delete_project_with_character(client):
    """Deleting a project that has a CharacterProfile must not FK-violate."""
    pid, frame, _ = await _project_with_images(client)
    await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/promote",
        json={"target": "character_ref", "name": "Hero"},
    )
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
