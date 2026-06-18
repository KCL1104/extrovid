"""r2v consistency tests — offline (mock). Promote a concept frame to a character, then
generate a shot referencing it and confirm it routes to wan2.7-r2v."""

from app.providers.video_factory import _build_r2v_media


def test_r2v_media_never_drops_the_first_frame_seed():
    """A full set of references must not crowd out the continuation/keyframe seed."""
    refs = [f"u{i}" for i in range(5)]
    media = _build_r2v_media(refs, "seed")
    assert len(media) == 5  # provider's media-array limit
    assert sum(1 for m in media if m["type"] == "reference_image") == 4  # one slot reserved
    assert media[-1] == {"type": "first_frame", "url": "seed"}  # seed survives
    # with no seed, references may fill all five slots
    no_seed = _build_r2v_media(refs, None)
    assert len(no_seed) == 5
    assert all(m["type"] == "reference_image" for m in no_seed)


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
    hero = next(c for c in chars if c["name"] == "Hero")  # auto-extracted cast coexists
    assert len(hero["reference_image_urls"]) >= 1


async def test_generate_shot_with_character_uses_r2v(client):
    pid, frame, shot_ids = await _project_with_images(client)
    await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/promote",
        json={"target": "character_ref", "name": "Hero"},
    )
    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    char_id = next(c["id"] for c in chars if c["name"] == "Hero")
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
