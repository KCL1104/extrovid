"""Shot-to-shot continuation: previous take's last frame seeds the next shot's i2v."""


async def _project_with_storyboard(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "Cont"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s coffee teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, [s["id"] for s in shots]


async def test_continue_from_previous_routes_to_i2v(client):
    pid, shot_ids = await _project_with_storyboard(client)
    # render shot 0 first, then continue shot 1 from it
    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_ids[1]}/generate",
        json={"continue_from_previous": True},
    )
    assert r.status_code == 200
    v = r.json()
    assert "continues from shot #0" in v["routing_note"]
    assert v["model"].endswith("i2v")  # first-frame input forces the i2v model


async def test_continue_without_previous_take_400(client):
    pid, shot_ids = await _project_with_storyboard(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_ids[0]}/generate",
        json={"continue_from_previous": True},
    )
    assert r.status_code == 400
    assert "continue" in r.json()["detail"]


async def test_plain_generate_unaffected(client):
    pid, shot_ids = await _project_with_storyboard(client)
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")).json()
    assert "continues from" not in (v["routing_note"] or "")


async def test_continuation_composes_with_cast(client):
    """cast + continue together: r2v with the previous take's last frame as the seed."""
    pid, shot_ids = await _project_with_storyboard(client)
    # build a character from a generated concept frame
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]
    await client.post(f"/api/projects/{pid}/concept-sets/{cs['id']}/generate-images")
    frame = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["look_frames"][0]
    await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/promote",
        json={"target": "character_ref", "name": "Hero"},
    )
    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    char_id = next(c["id"] for c in chars if c["name"] == "Hero")

    await client.post(f"/api/projects/{pid}/shots/{shot_ids[0]}/generate")
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_ids[1]}/generate",
        json={"continue_from_previous": True, "character_id": char_id},
    )
    assert r.status_code == 200
    v = r.json()
    assert v["model"].endswith("r2v")  # consistency wins the mode
    assert v["routing_note"].startswith("r2v")
    assert "continues from shot #0" in v["routing_note"]  # ...and the seed still applies
