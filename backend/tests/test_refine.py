"""Qwen-Image-Edit look-frame refinement: new frame, kept lineage, cap-checked."""

from app.core.config import get_settings


async def _frame_with_image(client) -> tuple[str, str, dict]:
    pid = (await client.post("/api/projects", json={"title": "Refine"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]
    await client.post(f"/api/projects/{pid}/concept-sets/{cs['id']}/generate-images")
    cs = next(
        c
        for c in (await client.get(f"/api/projects/{pid}/concept-sets")).json()
        if c["id"] == cs["id"]
    )
    return pid, cs["id"], cs["look_frames"][0]


async def test_refine_creates_child_frame(client):
    pid, cs_id, frame = await _frame_with_image(client)
    r = await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/refine",
        json={"instruction": "make the lighting golden hour"},
    )
    assert r.status_code == 200
    refined = r.json()
    assert refined["id"] != frame["id"]
    assert refined["parent_frame_id"] == frame["id"]
    assert refined["image_asset_id"]
    assert "golden hour" in refined["prompt"]
    assert "refined" in refined["tags"]

    # the refined frame joins the same concept set
    sets = (await client.get(f"/api/projects/{pid}/concept-sets")).json()
    cs = next(c for c in sets if c["id"] == cs_id)
    assert any(f["id"] == refined["id"] for f in cs["look_frames"])


async def test_refine_requires_generated_image(client):
    pid = (await client.post("/api/projects", json={"title": "NoImg"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]
    frame_id = cs["look_frames"][0]["id"]
    r = await client.post(
        f"/api/projects/{pid}/look-frames/{frame_id}/refine",
        json={"instruction": "warmer"},
    )
    assert r.status_code == 400


async def test_refine_counts_against_image_cap(client):
    pid, _cs_id, frame = await _frame_with_image(client)  # consumed 4 images today
    s = get_settings()
    prev = s.daily_image_cap
    s.daily_image_cap = 4  # budget exactly exhausted by the concept set
    try:
        r = await client.post(
            f"/api/projects/{pid}/look-frames/{frame['id']}/refine",
            json={"instruction": "warmer"},
        )
        assert r.status_code == 429
    finally:
        s.daily_image_cap = prev


async def test_concept_set_carries_visual_brief(client):
    pid = (await client.post("/api/projects", json={"title": "VB"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]
    vb = cs["visual_brief"]
    assert vb and vb["visual_style"] and vb["lighting"] and vb["palette"]
