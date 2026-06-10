"""Best-of-N take fan-out + review-driven auto-select. Offline (mock video + review)."""


async def _project_with_shots(client):
    pid = (await client.post("/api/projects", json={"title": "FanOut"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_fanout_creates_n_takes_sharing_a_batch(client):
    pid, shot_ids = await _project_with_shots(client)
    r = await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate", json={"num_takes": 3})
    assert r.status_code == 200
    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions")).json()
    assert len(versions) == 3
    # exactly one winner auto-selected once the whole batch landed (mock = instant)
    assert sum(1 for v in versions if v["selected"]) == 1
    winner = next(v for v in versions if v["selected"])
    assert winner["score"] is not None  # the pick is review-driven


async def test_single_take_is_not_auto_selected(client):
    pid, shot_ids = await _project_with_shots(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate", json={})
    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions")).json()
    assert len(versions) == 1
    assert versions[0]["selected"] is False  # selection stays an explicit act for N=1


async def test_manual_selection_is_never_overridden(client):
    pid, shot_ids = await _project_with_shots(client)
    sid = shot_ids[0]
    await client.post(f"/api/projects/{pid}/shots/{sid}/generate", json={})
    first = (await client.get(f"/api/projects/{pid}/shots/{sid}/versions")).json()[0]
    await client.post(f"/api/projects/{pid}/shots/{sid}/versions/{first['id']}/select")

    await client.post(f"/api/projects/{pid}/shots/{sid}/generate", json={"num_takes": 2})
    versions = (await client.get(f"/api/projects/{pid}/shots/{sid}/versions")).json()
    assert len(versions) == 3
    selected = [v for v in versions if v["selected"]]
    assert len(selected) == 1
    assert selected[0]["id"] == first["id"]  # the manual pick stood


async def test_num_takes_validation(client):
    pid, shot_ids = await _project_with_shots(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_ids[0]}/generate", json={"num_takes": 9}
    )
    assert r.status_code == 422
