"""SSE live streaming: director tool events + project job-progress. Offline (mock)."""

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agents.director_agent import director_agent
from app.core import event_bus


def _scripted_tool_caller():
    """A director model that calls one real tool, then replies — so the stream actually
    emits tool events (the default dispatch_mock calls NO tools)."""
    state = {"n": 0}

    def fn(messages, info):
        state["n"] += 1
        if state["n"] == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name="get_project_state", args={})])
        return ModelResponse(parts=[TextPart(content="Here is your project state.")])

    return fn


async def _project(client) -> str:
    pid = (await client.post("/api/projects", json={"title": "Stream"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    return pid


async def test_director_stream_emits_tool_events_then_done(client):
    pid = await _project(client)
    body = ""
    with director_agent.override(model=FunctionModel(_scripted_tool_caller())):
        async with client.stream(
            "POST", f"/api/projects/{pid}/director/stream", json={"message": "status?"}
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            async for chunk in resp.aiter_text():
                body += chunk
    assert "tool_start" in body
    assert "get_project_state" in body  # the tool the scripted model called
    assert "tool_result" in body
    assert '"type": "done"' in body
    assert "Here is your project state." in body  # the final reply rides on `done`


async def test_director_stream_persists_the_turn(client):
    pid = await _project(client)
    with director_agent.override(model=FunctionModel(_scripted_tool_caller())):
        async with client.stream(
            "POST", f"/api/projects/{pid}/director/stream", json={"message": "hello"}
        ) as resp:
            async for _ in resp.aiter_text():
                pass
    turns = (await client.get(f"/api/projects/{pid}/director/turns")).json()
    assert turns[-2]["role"] == "user" and turns[-2]["content"] == "hello"
    assert turns[-1]["role"] == "assistant"


def test_event_bus_fans_out_and_cleans_up():
    q = event_bus.subscribe("p1")
    event_bus.publish("p1", {"type": "job", "shot_id": "s1"})
    assert q.get_nowait()["shot_id"] == "s1"
    event_bus.unsubscribe("p1", q)
    event_bus.publish("p1", {"type": "job"})  # no subscribers — must not raise
    assert q.empty()


async def test_generate_publishes_a_job_event(client):
    pid = await _project(client)
    sid = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]["id"]
    q = event_bus.subscribe(pid)
    try:
        await client.post(f"/api/projects/{pid}/shots/{sid}/generate", json={})
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        assert any(e.get("type") == "job" and e.get("shot_id") == sid for e in events)
    finally:
        event_bus.unsubscribe(pid, q)


# NOTE: the /events endpoint is an INFINITE SSE stream; httpx's ASGITransport buffers the
# whole response before yielding, so it can't be consumed incrementally in-process (it
# hangs). The wiring is covered by the bus + publish tests above; the live endpoint is
# verified in a real browser. (The director stream IS testable here — it's finite.)
