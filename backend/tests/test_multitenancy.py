"""Per-user multi-tenancy: auto-naming, isolation, admin-sees-all, per-user caps, rotation.

Uses raw_client (real auth) and registers real accounts so ownership + token lookup are
exercised end-to-end. LLM/image/video are mocked, so generation is free.
"""

import pytest

from app.core.config import get_settings


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(raw_client, email: str) -> str:
    r = await raw_client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


@pytest.fixture
def admin_token():
    s = get_settings()
    prev = s.api_token
    s.api_token = "admin-secret"
    yield "admin-secret"
    s.api_token = prev


async def test_auto_naming(raw_client):
    t = await _register(raw_client, "namer@b.com")
    p1 = await raw_client.post("/api/projects", json={}, headers=_hdr(t))
    p2 = await raw_client.post("/api/projects", json={}, headers=_hdr(t))
    assert p1.json()["title"] == "Project 1"
    assert p2.json()["title"] == "Project 2"
    assert p1.json()["owner_id"] == p2.json()["owner_id"]


async def test_explicit_title_respected(raw_client):
    t = await _register(raw_client, "titler@b.com")
    p = await raw_client.post("/api/projects", json={"title": "My Film"}, headers=_hdr(t))
    assert p.json()["title"] == "My Film"


async def test_user_isolation(raw_client):
    ta = await _register(raw_client, "a@iso.com")
    tb = await _register(raw_client, "b@iso.com")
    pa = (await raw_client.post("/api/projects", json={}, headers=_hdr(ta))).json()["id"]
    # B sees none of A's projects, and gets 404 (not 403) on a direct fetch.
    assert (await raw_client.get("/api/projects", headers=_hdr(tb))).json() == []
    assert (await raw_client.get(f"/api/projects/{pa}", headers=_hdr(tb))).status_code == 404
    # A sees and can fetch their own.
    assert len((await raw_client.get("/api/projects", headers=_hdr(ta))).json()) == 1
    assert (await raw_client.get(f"/api/projects/{pa}", headers=_hdr(ta))).status_code == 200


async def test_admin_sees_all(raw_client, admin_token):
    ta = await _register(raw_client, "x@admin.com")
    pa = (await raw_client.post("/api/projects", json={}, headers=_hdr(ta))).json()["id"]
    listing = (await raw_client.get("/api/projects", headers=_hdr(admin_token))).json()
    assert pa in [p["id"] for p in listing]
    r = await raw_client.get(f"/api/projects/{pa}", headers=_hdr(admin_token))
    assert r.status_code == 200


async def test_rotate_token_invalidates_old(raw_client):
    t = await _register(raw_client, "rot@b.com")
    new = (await raw_client.post("/api/auth/rotate-token", headers=_hdr(t))).json()["token"]
    assert new != t
    assert (await raw_client.get("/api/auth/me", headers=_hdr(t))).status_code == 401
    assert (await raw_client.get("/api/auth/me", headers=_hdr(new))).status_code == 200


async def _storyboard_shots(raw_client, token, pid):
    await raw_client.post(
        f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"}, headers=_hdr(token)
    )
    resp = await raw_client.get(f"/api/projects/{pid}/storyboard", headers=_hdr(token))
    return [s["id"] for s in resp.json()]


async def _generate(raw_client, token, pid, shot_id):
    return await raw_client.post(
        f"/api/projects/{pid}/shots/{shot_id}/generate", headers=_hdr(token)
    )


async def test_per_user_video_cap_independent(raw_client):
    s = get_settings()
    prev = s.default_daily_video_cap
    s.default_daily_video_cap = 1  # newly-registered accounts get a video cap of 1
    try:
        ta = await _register(raw_client, "capa@b.com")
        tb = await _register(raw_client, "capb@b.com")
        pa = (await raw_client.post("/api/projects", json={}, headers=_hdr(ta))).json()["id"]
        shots = await _storyboard_shots(raw_client, ta, pa)
        assert (await _generate(raw_client, ta, pa, shots[0])).status_code == 200
        # A's second generation exceeds A's cap.
        assert (await _generate(raw_client, ta, pa, shots[1])).status_code == 429
        # B's counter is independent — B's first generation still succeeds.
        pb = (await raw_client.post("/api/projects", json={}, headers=_hdr(tb))).json()["id"]
        shotsb = await _storyboard_shots(raw_client, tb, pb)
        assert (await _generate(raw_client, tb, pb, shotsb[0])).status_code == 200
    finally:
        s.default_daily_video_cap = prev
