"""One-click Produce — the whole-pipeline orchestration walker (mock providers)."""

import asyncio


async def _planned_project(client) -> str:
    pid = (await client.post("/api/projects", json={"title": "Produce"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    assert r.status_code == 200
    return pid


async def _wait_for(client, pid: str, states: set[str], tries: int = 100) -> dict:
    for _ in range(tries):
        st = (await client.get(f"/api/projects/{pid}/produce")).json()
        if st["state"] in states:
            return st
        await asyncio.sleep(0.05)
    raise AssertionError(f"produce never reached {states}: {st}")


async def test_produce_auto_runs_to_rough_cut(client):
    pid = await _planned_project(client)
    r = await client.post(f"/api/projects/{pid}/produce", json={"mode": "auto"})
    assert r.status_code == 200
    st = await _wait_for(client, pid, {"done", "error", "paused"})
    assert st["state"] == "done", st
    # every stage's artifacts exist: keyframes, takes, and an assembled rough cut
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    assert shots and all(s["keyframe_frame_id"] for s in shots)
    cuts = (await client.get(f"/api/projects/{pid}/rough-cut")).json()
    assert len(cuts) >= 1


async def test_produce_gated_pauses_at_new_keyframes_then_resumes(client):
    pid = await _planned_project(client)
    await client.post(f"/api/projects/{pid}/produce", json={})  # default mode=gated
    st = await _wait_for(client, pid, {"paused", "done", "error"})
    assert st["state"] == "paused" and st["stage"] == "keyframes", st
    # keyframes exist but no video budget was spent yet
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    assert all(s["keyframe_frame_id"] for s in shots)
    versions = (
        await client.get(f"/api/projects/{pid}/shots/{shots[0]['id']}/versions")
    ).json()
    assert versions == []
    # Produce again: keyframes are now pre-existing, so the run continues to the cut
    await client.post(f"/api/projects/{pid}/produce", json={})
    st = await _wait_for(client, pid, {"done", "error"})
    assert st["state"] == "done", st
    assert len((await client.get(f"/api/projects/{pid}/rough-cut")).json()) >= 1


async def test_produce_requires_a_storyboard(client):
    pid = (await client.post("/api/projects", json={"title": "Empty"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/produce", json={"mode": "auto"})
    assert r.status_code == 422


async def test_produce_stop_reports_stopped(client):
    pid = await _planned_project(client)
    await client.post(f"/api/projects/{pid}/produce", json={"mode": "auto"})
    r = await client.post(f"/api/projects/{pid}/produce/stop")
    assert r.status_code == 200
    st = await _wait_for(client, pid, {"stopped", "done"})
    assert st["state"] in ("stopped", "done")
