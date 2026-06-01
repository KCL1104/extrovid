"""Image-layer tests — offline (USE_MOCK_IMAGE: mock generator + in-memory storage)."""

from app.providers.image_factory import generate_image, size_for_aspect


async def test_generate_image_mock_returns_png():
    result = await generate_image("a calm desk", size="928*1664")
    assert result.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    assert (result.width, result.height) == (928, 1664)
    assert result.source_model.startswith("mock:")


def test_size_for_aspect():
    assert size_for_aspect("9:16") == "928*1664"
    assert size_for_aspect("16:9") == "1664*928"
    assert size_for_aspect("unknown") == "1328*1328"


async def _run_pipeline(client) -> str:
    pid = (await client.post("/api/projects", json={"title": "Img"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    return pid


async def test_generate_concept_images_and_read(client):
    pid = await _run_pipeline(client)
    sets = (await client.get(f"/api/projects/{pid}/concept-sets")).json()
    assert sets and all(f["image_asset_id"] is None for f in sets[0]["look_frames"])
    cs_id = sets[0]["id"]

    r = await client.post(f"/api/projects/{pid}/concept-sets/{cs_id}/generate-images")
    assert r.status_code == 200
    frames = r.json()
    assert frames and all(f["image_asset_id"] for f in frames)
    assert all(f["image_url"] and f["image_url"].startswith("mock://") for f in frames)

    # re-read: set is GENERATED and frames now carry image URLs
    sets2 = (await client.get(f"/api/projects/{pid}/concept-sets")).json()
    target = next(c for c in sets2 if c["id"] == cs_id)
    assert target["status"] == "generated"
    assert all(f["image_url"] for f in target["look_frames"])


async def test_generate_images_respects_limit(client):
    pid = await _run_pipeline(client)
    cs_id = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["id"]
    frames = (
        await client.post(f"/api/projects/{pid}/concept-sets/{cs_id}/generate-images?limit=1")
    ).json()
    with_img = [f for f in frames if f["image_asset_id"]]
    assert len(with_img) == 1


async def test_generate_images_unknown_set_404(client):
    pid = await _run_pipeline(client)
    r = await client.post(f"/api/projects/{pid}/concept-sets/nope/generate-images")
    assert r.status_code == 404


async def test_promote_look_frame_to_style_pack(client):
    pid = await _run_pipeline(client)
    frame_id = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["look_frames"][0][
        "id"
    ]
    r = await client.post(
        f"/api/projects/{pid}/look-frames/{frame_id}/promote",
        json={"target": "style_pack", "name": "Warm Cinematic"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["promoted_as"] == "style_pack"
    assert "style_pack_id" in body


async def test_promote_rejects_none_target(client):
    pid = await _run_pipeline(client)
    frame_id = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["look_frames"][0][
        "id"
    ]
    r = await client.post(
        f"/api/projects/{pid}/look-frames/{frame_id}/promote", json={"target": "none"}
    )
    assert r.status_code == 422


async def test_delete_project_with_generated_images(client):
    """Deleting a project that has ImageAssets must not FK-violate."""
    pid = await _run_pipeline(client)
    cs_id = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["id"]
    await client.post(f"/api/projects/{pid}/concept-sets/{cs_id}/generate-images?limit=1")
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404
