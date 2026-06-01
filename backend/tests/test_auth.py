"""Shared-token auth tests. Default (api_token=None) leaves the API open so the rest of the
suite is unaffected; these tests enable a token and assert the gate."""

import pytest

from app.core.config import get_settings


@pytest.fixture
def token():
    s = get_settings()
    prev = s.api_token
    s.api_token = "test-secret"
    yield "test-secret"
    s.api_token = prev


async def test_health_open_without_token(client):
    assert (await client.get("/health")).status_code == 200


async def test_auth_disabled_by_default(client):
    # api_token is None -> /api stays open
    assert (await client.get("/api/projects")).status_code == 200


async def test_api_requires_token_when_set(client, token):
    assert (await client.get("/api/projects")).status_code == 401


async def test_api_wrong_token_401(client, token):
    r = await client.get("/api/projects", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_api_correct_token_ok(client, token):
    r = await client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_health_open_even_with_token(client, token):
    assert (await client.get("/health")).status_code == 200
