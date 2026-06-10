"""API integration tests — exercised against the test database, LLM mocked."""

from app.models.enums import MAX_SHOTS_PER_SCENE, MIN_SHOTS_PER_SCENE, ProjectStatus


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_project_crud_roundtrip(client):
    # create
    r = await client.post("/api/projects", json={"title": "Coffee Ad", "target_duration_sec": 30})
    assert r.status_code == 201
    project = r.json()
    pid = project["id"]
    assert project["title"] == "Coffee Ad"
    assert project["status"] == ProjectStatus.DRAFT.value

    # read
    r = await client.get(f"/api/projects/{pid}")
    assert r.status_code == 200

    # list
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())

    # update
    r = await client.patch(f"/api/projects/{pid}", json={"title": "Coffee Ad v2"})
    assert r.status_code == 200
    assert r.json()["title"] == "Coffee Ad v2"

    # delete + 404
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    r = await client.get(f"/api/projects/{pid}")
    assert r.status_code == 404


async def test_get_missing_project_404(client):
    r = await client.get("/api/projects/does-not-exist")
    assert r.status_code == 404


async def test_run_pipeline_end_to_end(client):
    # create a project
    r = await client.post("/api/projects", json={"title": "Coffee Ad"})
    pid = r.json()["id"]

    # run the full Brief -> Storyboard pipeline (mocked LLM)
    r = await client.post(
        f"/api/projects/{pid}/run",
        json={"raw_prompt": "a 30s vertical product ad for a coffee brand"},
    )
    assert r.status_code == 200
    result = r.json()
    assert result["brief"]["target_duration_sec"] == 30
    shots = [s for sc in result["storyboard"]["scenes"] for s in sc["shots"]]
    n_scenes = len(result["script"]["scenes"])
    assert MIN_SHOTS_PER_SCENE * n_scenes <= len(shots) <= MAX_SHOTS_PER_SCENE * n_scenes

    # project advanced to storyboarded
    r = await client.get(f"/api/projects/{pid}")
    assert r.json()["status"] == ProjectStatus.STORYBOARDED.value

    # persisted storyboard reads back, contiguous order
    r = await client.get(f"/api/projects/{pid}/storyboard")
    assert r.status_code == 200
    stored = r.json()
    assert len(stored) == len(shots)
    assert sorted(s["order"] for s in stored) == list(range(len(stored)))
    assert all(s["preferred_model"] in ("wan2.7-t2v", "wan2.7-i2v") for s in stored)

    # concept sets persisted, every look frame has no image asset (Milestone 1)
    r = await client.get(f"/api/projects/{pid}/concept-sets")
    assert r.status_code == 200
    concept_sets = r.json()
    assert len(concept_sets) >= 1
    for cs in concept_sets:
        assert 4 <= len(cs["look_frames"]) <= 8
        assert all(f["image_asset_id"] is None for f in cs["look_frames"])

    # scenes persisted
    r = await client.get(f"/api/projects/{pid}/script")
    assert r.status_code == 200
    assert len(r.json()) == len(concept_sets)


async def test_run_pipeline_is_idempotent(client):
    """Running twice replaces, not duplicates, the persisted slices."""
    r = await client.post("/api/projects", json={"title": "Rerun"})
    pid = r.json()["id"]
    body = {"raw_prompt": "a 20s teaser"}

    await client.post(f"/api/projects/{pid}/run", json=body)
    first = await client.get(f"/api/projects/{pid}/storyboard")
    await client.post(f"/api/projects/{pid}/run", json=body)
    second = await client.get(f"/api/projects/{pid}/storyboard")

    assert len(first.json()) == len(second.json())  # replaced, not appended
