"""Auth gate tests (real auth, no override — uses raw_client).

The API is never open now: every /api call needs either the env admin token or a per-user
token. /health stays public. register/login mint usable per-user tokens.
"""

import pytest

from app.core.config import get_settings


@pytest.fixture
def admin_token():
    s = get_settings()
    prev = s.api_token
    s.api_token = "admin-secret"
    yield "admin-secret"
    s.api_token = prev


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_health_open(raw_client):
    assert (await raw_client.get("/health")).status_code == 200


async def test_api_requires_auth_by_default(raw_client):
    # No admin token, no user token -> 401 (the API is not open by default anymore).
    assert (await raw_client.get("/api/projects")).status_code == 401


async def test_admin_token_grants_access(raw_client, admin_token):
    r = await raw_client.get("/api/projects", headers=_hdr(admin_token))
    assert r.status_code == 200


async def test_wrong_token_401(raw_client, admin_token):
    r = await raw_client.get("/api/projects", headers=_hdr("nope"))
    assert r.status_code == 401


async def test_register_returns_usable_token(raw_client):
    r = await raw_client.post(
        "/api/auth/register", json={"email": "a@b.com", "password": "password123"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "a@b.com"
    assert body["user"]["daily_video_cap"] == 3
    token = body["token"]
    me = await raw_client.get("/api/auth/me", headers=_hdr(token))
    assert me.status_code == 200
    assert me.json()["email"] == "a@b.com"


async def test_register_validates(raw_client):
    assert (
        await raw_client.post(
            "/api/auth/register", json={"email": "not-an-email", "password": "password123"}
        )
    ).status_code == 422
    assert (
        await raw_client.post("/api/auth/register", json={"email": "x@y.com", "password": "short"})
    ).status_code == 422


async def test_register_duplicate_email_409(raw_client):
    await raw_client.post(
        "/api/auth/register", json={"email": "dup@b.com", "password": "password123"}
    )
    r = await raw_client.post(
        "/api/auth/register", json={"email": "dup@b.com", "password": "password123"}
    )
    assert r.status_code == 409


async def test_login_flow(raw_client):
    await raw_client.post(
        "/api/auth/register", json={"email": "log@b.com", "password": "password123"}
    )
    ok = await raw_client.post(
        "/api/auth/login", json={"email": "log@b.com", "password": "password123"}
    )
    assert ok.status_code == 200
    assert ok.json()["token"]
    bad = await raw_client.post(
        "/api/auth/login", json={"email": "log@b.com", "password": "wrong-pass"}
    )
    assert bad.status_code == 401
