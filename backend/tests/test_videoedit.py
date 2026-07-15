"""videoedit (NL shot revision) tests — offline (mock). Edits a generated take into a new
take that preserves lineage and routes to the active provider's video-edit model
(happyhorse-1.0-video-edit by default; wan2.7-videoedit under VIDEO_PROVIDER=wan)."""

from app.core.config import Settings
from app.providers import video_factory


async def _shot_with_take(client):
    pid = (await client.post("/api/projects", json={"title": "Edit"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shot_id = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]["id"]
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_id}/generate")).json()
    return pid, shot_id, v


async def test_edit_creates_new_take_via_videoedit(client):
    pid, shot_id, v = await _shot_with_take(client)
    assert v["output_asset_id"]  # mock generate succeeded
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit",
        json={"instruction": "change the background to night"},
    )
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != v["id"]
    # provider-agnostic: wan2.7-videoedit / happyhorse-1.0-video-edit both contain "edit"
    assert "edit" in (new["model"] or "")

    versions = (await client.get(f"/api/projects/{pid}/shots/{shot_id}/versions")).json()
    assert len(versions) == 2


async def test_edit_unknown_source_400(client):
    pid, shot_id, _ = await _shot_with_take(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/nope/edit",
        json={"instruction": "relight warmer"},
    )
    assert r.status_code == 400


async def test_edit_requires_instruction(client):
    pid, shot_id, v = await _shot_with_take(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit", json={"instruction": ""}
    )
    assert r.status_code == 422


# --- request-body conformance (direct unit tests against the transport) ----------------------
# USE_MOCK_VIDEO short-circuits submit_videoedit() before a body is ever built, so the routing
# tests above never see the request we send — which is exactly how four conformance bugs
# survived. These capture the outgoing json= payload from _submit_dashscope_edit directly.


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"output": {"task_id": "task-123"}}


def _capture_edit_body(monkeypatch):
    """Patch the edit path's transport + rate limiter; return a dict the fake fills with the
    outgoing request. Patch the name resolved inside video_factory (it did a `from app.core.http
    import request_with_retry`, so patching app.core.http would miss the bound name). The
    rate-limiter no-op avoids the real 30s inter-request spacing (video_rpm=2)."""
    captured: dict = {}

    async def _fake_request(method, url, *, headers=None, json=None, timeout_sec=60, client=None):
        captured.update(method=method, url=url, headers=headers, json=json)
        return _FakeResp()

    async def _noop_acquire(_service):
        return None

    monkeypatch.setattr(video_factory, "request_with_retry", _fake_request)
    monkeypatch.setattr(video_factory.rate_limit, "acquire", _noop_acquire)
    return captured


def _edit_settings(**over) -> Settings:
    base = {"video_provider": "happyhorse", "video_resolution": "1080P", "dashscope_api_key": "k"}
    base.update(over)
    return Settings(**base)


async def test_edit_body_watermark_off_audio_origin_no_prompt_extend(monkeypatch):
    captured = _capture_edit_body(monkeypatch)
    await video_factory._submit_dashscope_edit(
        _edit_settings(), "happyhorse-1.0-video-edit", "https://v/src.mp4", "relight warmer"
    )
    params = captured["json"]["parameters"]
    assert params["watermark"] is False
    assert params["audio_setting"] == "origin"  # default: keep the take's native audio
    assert "prompt_extend" not in params  # dropped — not a video-edit parameter
    media = captured["json"]["input"]["media"]
    assert [m["type"] for m in media] == ["video"]  # exactly one video, no stray refs
    assert media[0]["url"] == "https://v/src.mp4"


async def test_edit_body_audio_auto_when_touches_audio(monkeypatch):
    captured = _capture_edit_body(monkeypatch)
    await video_factory._submit_dashscope_edit(
        _edit_settings(),
        "happyhorse-1.0-video-edit",
        "https://v/src.mp4",
        "add distant thunder",
        audio_setting="auto",
    )
    assert captured["json"]["parameters"]["audio_setting"] == "auto"


async def test_edit_body_reference_images_capped_at_5_portrait_survives(monkeypatch):
    captured = _capture_edit_body(monkeypatch)
    # slot 0 is the identity portrait upstream; pass 8 candidates to force truncation
    refs = [f"https://v/ref{i}.png" for i in range(8)]
    await video_factory._submit_dashscope_edit(
        _edit_settings(), "happyhorse-1.0-video-edit", "https://v/src.mp4", "swap outfit",
        reference_urls=refs,
    )
    media = captured["json"]["input"]["media"]
    ref_items = [m for m in media if m["type"] == "reference_image"]
    assert media[0]["type"] == "video"
    assert len(ref_items) == 5  # HappyHorse cap, not r2v's 9
    assert ref_items[0]["url"] == "https://v/ref0.png"  # slot-0 portrait survives truncation
    assert [m["type"] for m in media] == ["video"] + ["reference_image"] * 5


async def test_edit_body_wan_stays_within_wan_doc(monkeypatch):
    """VIDEO_PROVIDER=wan: watermark + audio_setting are Wan-accepted (wan-video-editing-api-
    reference), prompt_extend is absent, and references cap at Wan's 4 — not HappyHorse's 5."""
    captured = _capture_edit_body(monkeypatch)
    refs = [f"https://v/ref{i}.png" for i in range(8)]
    await video_factory._submit_dashscope_edit(
        _edit_settings(video_provider="wan"), "wan2.7-videoedit", "https://v/src.mp4",
        "change background to night", reference_urls=refs,
    )
    body = captured["json"]
    params = body["parameters"]
    # only fields the Wan video-edit doc documents; prompt_extend intentionally omitted
    assert set(params) == {"resolution", "watermark", "audio_setting"}
    assert params["watermark"] is False
    assert params["audio_setting"] == "origin"
    ref_items = [m for m in body["input"]["media"] if m["type"] == "reference_image"]
    assert len(ref_items) == 4  # Wan cap


async def test_edit_touches_audio_maps_to_audio_setting(client, monkeypatch):
    """End-to-end through the API: EditShotRequest.touches_audio → submit_shot_edit → the
    audio_setting handed to the provider. This is the seam ABOVE _submit_dashscope_edit that the
    body tests can't reach (mock video short-circuits the body), so spy on the provider call."""
    from app.providers import video_factory
    from app.services import generate_service

    captured: dict = {}
    real = video_factory.submit_videoedit

    async def _spy(source_video_url, prompt, *, reference_urls=None, audio_setting="origin"):
        captured["audio_setting"] = audio_setting
        return await real(
            source_video_url, prompt, reference_urls=reference_urls, audio_setting=audio_setting
        )

    monkeypatch.setattr(generate_service, "submit_videoedit", _spy)

    pid, shot_id, v = await _shot_with_take(client)
    await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit",
        json={"instruction": "relight warmer"},
    )
    assert captured["audio_setting"] == "origin"  # default preserves the take's native audio

    await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit",
        json={"instruction": "add distant thunder", "touches_audio": True},
    )
    assert captured["audio_setting"] == "auto"  # opt-in lets the model re-decide sound


async def test_retry_edit_reproduces_audio_setting(client, monkeypatch):
    """A retried edit reproduces the take's audio behavior: submit_shot_edit records the
    resolved audio_setting in gen_params, and retry_job maps it back to touches_audio so the
    re-submit is identical (docstring promise). Uses the failure->retry pattern (real-mode
    submit faked so the edit job stays RUNNING and can be failed)."""
    from app.core.config import get_settings
    from app.providers.video_factory import PollResult, SubmitResult
    from app.services import generate_service

    pid, shot_id, v = await _shot_with_take(client)

    captured: dict = {}

    async def _spy(source_video_url, prompt, *, reference_urls=None, audio_setting="origin"):
        captured["audio_setting"] = audio_setting
        return SubmitResult(task_id="t-edit-fail", model="happyhorse-1.0-video-edit")

    async def _fail_poll(_task_id):
        return PollResult(status="FAILED", failure="provider exploded")

    s = get_settings()
    prev = s.use_mock_video
    s.use_mock_video = False  # keep the edit job RUNNING after submit so it can fail
    monkeypatch.setattr(generate_service, "submit_videoedit", _spy)
    monkeypatch.setattr(generate_service, "poll_video", _fail_poll)
    try:
        edit = (
            await client.post(
                f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit",
                json={"instruction": "add rain sound", "touches_audio": True},
            )
        ).json()
        assert captured["audio_setting"] == "auto"  # first submit carries the intent
        failed = (
            await client.post(f"/api/projects/{pid}/jobs/{edit['job_id']}/refresh")
        ).json()
        assert failed["job_status"] == "failed"

        captured.clear()
        r = await client.post(f"/api/projects/{pid}/jobs/{edit['job_id']}/retry")
        assert r.status_code == 200
        # retry rebuilt touches_audio=True from gen_params["audio_setting"] == "auto"
        assert captured["audio_setting"] == "auto"
    finally:
        s.use_mock_video = prev
