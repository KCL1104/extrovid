"""ReviewAgent loop — every finished take gets a score + director's notes (mock LLM)."""


async def _project_with_storyboard(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "Review"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_auto_review_on_mock_generate(client):
    pid, shot_ids = await _project_with_storyboard(client)
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions")).json()
    v = versions[0]
    assert v["score"] is not None and 0 <= v["score"] <= 10
    assert v["review"]["verdict"] in ("pass", "revise")
    assert v["review"]["notes"]
    assert v["status"] == "accepted"  # mock review passes -> accepted


async def test_manual_rereview_endpoint(client):
    pid, shot_ids = await _project_with_storyboard(client)
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")).json()
    r = await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions/{v['id']}/review")
    assert r.status_code == 200
    body = r.json()
    assert body["review"]["verdict"] == "pass"
    assert body["score"] == body["review"]["score"]


async def test_review_unknown_version_404(client):
    pid, shot_ids = await _project_with_storyboard(client)
    r = await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/versions/nope/review")
    assert r.status_code == 404


async def test_routing_note_recorded(client):
    pid, shot_ids = await _project_with_storyboard(client)
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")).json()
    assert v["routing_note"]
    assert v["routing_note"].split(" ")[0] in ("t2v", "i2v", "r2v")
