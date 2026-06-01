"""Usage visibility + daily cap (429) tests. Per-test DB reset keeps counts isolated."""

import pytest

from app.core.config import get_settings


async def _project_with_shots(client) -> tuple[str, list[str]]:
    pid = (await client.post("/api/projects", json={"title": "U"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = [s["id"] for s in (await client.get(f"/api/projects/{pid}/storyboard")).json()]
    return pid, shots


async def test_usage_starts_empty(client):
    u = (await client.get("/api/usage")).json()
    assert u["videos_today"] == 0
    assert u["images_today"] == 0
    assert u["est_spend_usd"] == 0
    assert u["video_cap"] >= 1


async def test_usage_counts_after_generate(client):
    pid, shots = await _project_with_shots(client)
    await client.post(f"/api/projects/{pid}/shots/{shots[0]}/generate")
    u = (await client.get("/api/usage")).json()
    assert u["videos_today"] >= 1
    assert "failed_today" in u
    assert u["est_spend_usd"] == 0  # mock generation is free (real cost computed per job)


@pytest.fixture
def video_cap_1():
    s = get_settings()
    prev = s.daily_video_cap
    s.daily_video_cap = 1
    yield
    s.daily_video_cap = prev


async def test_video_cap_returns_429(client, video_cap_1):
    pid, shots = await _project_with_shots(client)
    r1 = await client.post(f"/api/projects/{pid}/shots/{shots[0]}/generate")
    assert r1.status_code == 200
    r2 = await client.post(f"/api/projects/{pid}/shots/{shots[1]}/generate")
    assert r2.status_code == 429
    assert "cap" in r2.json()["detail"].lower()


@pytest.fixture
def image_cap_1():
    s = get_settings()
    prev = s.daily_image_cap
    s.daily_image_cap = 1
    yield
    s.daily_image_cap = prev


async def test_image_cap_returns_429(client, image_cap_1):
    pid, _ = await _project_with_shots(client)
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["id"]
    # a concept set has 4-8 frames > cap of 1 -> blocked
    r = await client.post(f"/api/projects/{pid}/concept-sets/{cs}/generate-images")
    assert r.status_code == 429
