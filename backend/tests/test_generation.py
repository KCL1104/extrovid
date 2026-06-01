"""Shot video generation tests — offline (USE_MOCK_VIDEO: instant fake MP4)."""


async def _project_with_storyboard(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "Gen"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_generate_shot_mock(client):
    pid, shot_ids = await _project_with_storyboard(client)
    r = await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    assert r.status_code == 200
    v = r.json()
    assert v["job_status"] == "succeeded"
    assert v["output_asset_id"]
    assert v["video_url"].startswith("mock://")
    assert v["model"].startswith("mock:")

    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions")).json()
    assert len(versions) == 1
    assert versions[0]["video_url"].startswith("mock://")


async def test_generate_creates_new_version_each_call(client):
    pid, shot_ids = await _project_with_storyboard(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions")).json()
    assert len(versions) == 2


async def test_refresh_job(client):
    pid, shot_ids = await _project_with_storyboard(client)
    job_id = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")).json()[
        "job_id"
    ]
    r = await client.post(f"/api/projects/{pid}/jobs/{job_id}/refresh")
    assert r.status_code == 200
    assert r.json()["job_status"] == "succeeded"


async def test_generate_unknown_shot_404(client):
    pid, _ = await _project_with_storyboard(client)
    r = await client.post(f"/api/projects/{pid}/shots/nope/generate")
    assert r.status_code == 404


async def test_delete_project_with_shot_versions(client):
    """Deleting a project that has ShotVersions/GenerationJobs/video assets must not FK-violate."""
    pid, shot_ids = await _project_with_storyboard(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
