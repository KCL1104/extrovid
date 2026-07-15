"""Video provider seam — offline (mock). Both providers ride the same DashScope transport and
differ only by model id. HappyHorse is the default (1.1 for t2v/i2v/r2v, 1.0 for video-edit);
VIDEO_PROVIDER=wan flips every mode back to Wan. These lock the dispatch +
mode resolution and that a flag flip carries through generate -> ingest -> take.model.
"""

import pytest

from app.core.config import Settings, get_settings
from app.providers import video_factory
from app.providers.video_factory import _resolve_video_model


def test_resolve_model_maps_mode_to_provider(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "video_provider", "happyhorse")
    assert "happyhorse-1.1-t2v" in _resolve_video_model(s, "t2v")
    assert "happyhorse-1.1-i2v" in _resolve_video_model(s, "i2v")
    assert "happyhorse-1.1-r2v" in _resolve_video_model(s, "r2v")
    assert "happyhorse-1.0-video-edit" == _resolve_video_model(s, "videoedit")

    monkeypatch.setattr(s, "video_provider", "wan")
    assert _resolve_video_model(s, "t2v") == s.wan_t2v_model
    assert _resolve_video_model(s, "i2v") == s.wan_i2v_model
    assert _resolve_video_model(s, "r2v") == s.wan_r2v_model
    assert _resolve_video_model(s, "videoedit") == s.wan_videoedit_model


def test_video_provider_default_is_happyhorse():
    assert Settings().video_provider == "happyhorse"


def test_video_provider_rejects_unknown():
    with pytest.raises(ValueError):
        Settings(video_provider="midjourney")
    assert Settings(video_provider="HAPPYHORSE").video_provider == "happyhorse"  # normalized


async def _shot_with_take(client):
    pid = (await client.post("/api/projects", json={"title": "HH"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shot_id = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]["id"]
    v = (await client.post(f"/api/projects/{pid}/shots/{shot_id}/generate")).json()
    return pid, shot_id, v


async def test_default_generate_routes_to_happyhorse(client):
    """Default provider — a plain (t2v) shot routes to HappyHorse."""
    _pid, _shot_id, v = await _shot_with_take(client)
    assert v["output_asset_id"]  # mock generate succeeded
    assert "happyhorse" in (v["model"] or "")


async def test_default_videoedit_routes_to_happyhorse(client):
    pid, shot_id, v = await _shot_with_take(client)
    r = await client.post(
        f"/api/projects/{pid}/shots/{shot_id}/versions/{v['id']}/edit",
        json={"instruction": "change the background to night"},
    )
    assert r.status_code == 200
    new = r.json()
    assert "happyhorse" in (new["model"] or "")
    assert "video-edit" in (new["model"] or "")


async def test_wan_override_routes_to_wan(client, monkeypatch):
    """VIDEO_PROVIDER=wan flips a plain shot back to the Wan model id."""
    monkeypatch.setattr(get_settings(), "video_provider", "wan")
    _pid, _shot_id, v = await _shot_with_take(client)
    assert "wan2.7" in (v["model"] or "")


# --- generation-path request body (t2v/i2v/r2v) ----------------------------------------------


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"output": {"task_id": "task-1"}}


def _capture_gen_body(monkeypatch) -> dict:
    captured: dict = {}

    async def _fake_request(method, url, *, headers=None, json=None, timeout_sec=60, client=None):
        captured.update(json=json)
        return _FakeResp()

    async def _noop_acquire(_service):
        return None

    monkeypatch.setattr(video_factory, "request_with_retry", _fake_request)
    monkeypatch.setattr(video_factory.rate_limit, "acquire", _noop_acquire)
    return captured


async def test_generation_watermark_gated_to_happyhorse(monkeypatch):
    """HappyHorse 1.1 t2v/i2v/r2v default watermark=true, so _submit_dashscope sends
    watermark:false; the Wan body is left untouched (its generation-path watermark is
    unconfirmed), so VIDEO_PROVIDER=wan stays exactly as before. prompt_extend legitimately
    stays on the generation path (unlike the edit path)."""
    captured = _capture_gen_body(monkeypatch)
    hh = Settings(video_provider="happyhorse", dashscope_api_key="k")
    await video_factory._submit_dashscope(
        hh, "happyhorse-1.1-t2v", "t2v", "a wide shot",
        ratio="9:16", duration=5, first_frame_url=None, refs=[], negative_prompt=None,
    )
    hh_params = captured["json"]["parameters"]
    assert hh_params["watermark"] is False
    assert hh_params["prompt_extend"] is True  # still expands short shot prompts

    wan = Settings(video_provider="wan", dashscope_api_key="k")
    await video_factory._submit_dashscope(
        wan, "wan2.7-t2v", "t2v", "a wide shot",
        ratio="9:16", duration=5, first_frame_url=None, refs=[], negative_prompt=None,
    )
    assert "watermark" not in captured["json"]["parameters"]  # Wan body untouched
