"""Public gallery: publish guard, ownership, public list (no auth), and video redirect.

The happy path needs a non-mock video asset; since the suite runs in mock mode, we patch
presigned_url to simulate a real bucket object so publish/stream can be exercised offline.
"""


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(raw_client, email: str) -> str:
    r = await raw_client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


async def _project_with_rough_cut(raw_client, token: str) -> tuple[str, dict]:
    pid = (await raw_client.post("/api/projects", json={}, headers=_hdr(token))).json()["id"]
    await raw_client.post(
        f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"}, headers=_hdr(token)
    )
    shots = (await raw_client.get(f"/api/projects/{pid}/storyboard", headers=_hdr(token))).json()
    await raw_client.post(
        f"/api/projects/{pid}/shots/{shots[0]['id']}/generate", headers=_hdr(token)
    )
    rc = (await raw_client.post(f"/api/projects/{pid}/rough-cut", headers=_hdr(token))).json()
    return pid, rc


async def test_public_gallery_empty_no_auth(raw_client):
    # The gallery list is public: no Authorization header, still 200.
    r = await raw_client.get("/api/gallery")
    assert r.status_code == 200
    assert r.json() == []


async def test_publish_mock_rough_cut_rejected(raw_client):
    t = await _register(raw_client, "mock@b.com")
    pid, rc = await _project_with_rough_cut(raw_client, t)
    r = await raw_client.post(
        f"/api/projects/{pid}/rough-cut/{rc['id']}/publish", headers=_hdr(t)
    )
    assert r.status_code == 400  # mock asset can't be published


async def test_publish_unknown_sequence_404(raw_client):
    t = await _register(raw_client, "nf@b.com")
    pid = (await raw_client.post("/api/projects", json={}, headers=_hdr(t))).json()["id"]
    r = await raw_client.post(
        f"/api/projects/{pid}/rough-cut/does-not-exist/publish", headers=_hdr(t)
    )
    assert r.status_code == 404


async def test_publish_list_and_stream(raw_client, monkeypatch):
    # Make any asset look like a real bucket object served at a stable URL.
    fake = "https://cdn.example/clip.mp4"
    monkeypatch.setattr("app.services.gallery_service.presigned_url", lambda key: fake)
    monkeypatch.setattr("app.api.gallery.presigned_url", lambda key: fake)

    t = await _register(raw_client, "pub@b.com")
    pid, rc = await _project_with_rough_cut(raw_client, t)

    pub = await raw_client.post(
        f"/api/projects/{pid}/rough-cut/{rc['id']}/publish", headers=_hdr(t)
    )
    assert pub.status_code == 200
    published_id = pub.json()["id"]
    assert pub.json()["stream_url"].endswith(f"/api/gallery/{published_id}/video")

    # Public listing (no auth) now contains it.
    listing = (await raw_client.get("/api/gallery")).json()
    assert published_id in [v["id"] for v in listing]

    # The rough-cut read reflects published state.
    cuts = (await raw_client.get(f"/api/projects/{pid}/rough-cut", headers=_hdr(t))).json()
    assert cuts[0]["published"] is True
    assert cuts[0]["published_id"] == published_id

    # Public stream endpoint 302-redirects to a freshly-minted URL (no auth, no follow).
    vid = await raw_client.get(f"/api/gallery/{published_id}/video")
    assert vid.status_code == 302
    assert vid.headers["location"] == fake

    # Unpublish removes it from the gallery.
    un = await raw_client.delete(
        f"/api/projects/{pid}/rough-cut/{rc['id']}/publish", headers=_hdr(t)
    )
    assert un.status_code == 204
    assert (await raw_client.get("/api/gallery")).json() == []


async def test_publish_others_project_404(raw_client, monkeypatch):
    monkeypatch.setattr("app.services.gallery_service.presigned_url", lambda key: "https://x/y.mp4")
    ta = await _register(raw_client, "owner@b.com")
    tb = await _register(raw_client, "intruder@b.com")
    pid, rc = await _project_with_rough_cut(raw_client, ta)
    # B cannot publish A's rough cut (project ownership gate → 404).
    r = await raw_client.post(
        f"/api/projects/{pid}/rough-cut/{rc['id']}/publish", headers=_hdr(tb)
    )
    assert r.status_code == 404
