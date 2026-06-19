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


async def test_delete_project_with_published_cut(client):
    """A project PUBLISHED to the gallery must delete cleanly: published_video FKs the cut's
    TimelineSequence (a published delete used to 500 with a FK violation on Postgres). The
    publish endpoint refuses mock videos, so seed the published_video row directly; assert it is
    gone after delete (catches the fix even on SQLite, which doesn't enforce the FK)."""
    from contextlib import aclosing

    from sqlalchemy import select

    from app.core.db import get_session
    from app.main import app
    from app.models.gallery import PublishedVideo

    pid, shot_ids = await _project_with_shots(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    cut = (await client.post(f"/api/projects/{pid}/rough-cut")).json()

    # seed the published_video row directly (publish endpoint refuses mock videos), closing the
    # session fully before the delete so it doesn't collide on the shared (StaticPool) connection
    async with aclosing(app.dependency_overrides[get_session]()) as gen:
        s = await gen.__anext__()
        s.add(
            PublishedVideo(
                project_id=pid,
                owner_id="test-user",
                timeline_sequence_id=cut["id"],
                output_asset_id="vid",
                title="t",
                aspect_ratio="16:9",
            )
        )
        await s.commit()

    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204

    async with aclosing(app.dependency_overrides[get_session]()) as gen:
        s = await gen.__anext__()
        left = (
            (await s.execute(select(PublishedVideo).where(PublishedVideo.project_id == pid)))
            .scalars()
            .all()
        )
    assert left == []  # the gallery share was cleaned up with the project
