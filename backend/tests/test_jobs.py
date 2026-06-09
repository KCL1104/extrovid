"""Project-wide generation queue: jobs list with shot context, retry semantics."""


async def _project_with_storyboard(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "Queue"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_jobs_list_with_shot_context(client):
    pid, shot_ids = await _project_with_storyboard(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[1]}/generate")

    r = await client.get(f"/api/projects/{pid}/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 2
    assert {j["status"] for j in jobs} == {"succeeded"}
    assert all(j["shot_purpose"] for j in jobs)
    assert sorted(j["shot_id"] for j in jobs) == sorted(shot_ids[:2])


async def test_jobs_list_empty_project(client):
    pid = (await client.post("/api/projects", json={"title": "Empty"})).json()["id"]
    r = await client.get(f"/api/projects/{pid}/jobs")
    assert r.status_code == 200
    assert r.json() == []


async def test_retry_rejects_non_failed_job(client):
    pid, shot_ids = await _project_with_storyboard(client)
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")).json()
    r = await client.post(f"/api/projects/{pid}/jobs/{v['job_id']}/retry")
    assert r.status_code == 400  # mock jobs succeed instantly; only failed jobs retry


async def test_retry_failed_job_creates_fresh_take(client, monkeypatch):
    """Full failure->retry loop: real-mode submit (faked), poll FAILED, retry succeeds."""
    from app.core.config import get_settings
    from app.providers.video_factory import PollResult, SubmitResult
    from app.services import generate_service

    pid, shot_ids = await _project_with_storyboard(client)

    s = get_settings()
    prev = s.use_mock_video
    s.use_mock_video = False  # job stays RUNNING after submit

    async def fake_submit(_prompt, **_kw):
        return SubmitResult(task_id="t-fail-1", model="wan2.7-t2v")

    async def fake_poll(_task_id):
        return PollResult(status="FAILED", failure="provider exploded")

    monkeypatch.setattr(generate_service, "submit_video", fake_submit)
    monkeypatch.setattr(generate_service, "poll_video", fake_poll)
    try:
        v = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")).json()
        assert v["job_status"] == "running"
        failed = (await client.post(f"/api/projects/{pid}/jobs/{v['job_id']}/refresh")).json()
        assert failed["job_status"] == "failed"
        assert failed["failure_reason"] == "provider exploded"
    finally:
        s.use_mock_video = prev

    # retry in mock mode -> a fresh take + fresh job that completes instantly
    r = await client.post(f"/api/projects/{pid}/jobs/{v['job_id']}/retry")
    assert r.status_code == 200
    fresh = r.json()
    assert fresh["id"] != v["id"]
    assert fresh["job_status"] == "succeeded"
    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions")).json()
    assert len(versions) == 2


async def test_jobs_404_for_other_users_project(raw_client):
    # register two users; user B cannot see user A's jobs
    a = (
        await raw_client.post(
            "/api/auth/register", json={"email": "a@x.io", "password": "password123"}
        )
    ).json()
    b = (
        await raw_client.post(
            "/api/auth/register", json={"email": "b@x.io", "password": "password123"}
        )
    ).json()
    ha = {"Authorization": f"Bearer {a['token']}"}
    hb = {"Authorization": f"Bearer {b['token']}"}
    pid = (await raw_client.post("/api/projects", json={"title": "A"}, headers=ha)).json()["id"]
    r = await raw_client.get(f"/api/projects/{pid}/jobs", headers=hb)
    assert r.status_code == 404
