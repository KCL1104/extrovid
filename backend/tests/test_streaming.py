"""SSE live streaming: director tool events + project job-progress. Offline (mock)."""

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.agents.director_agent import director_agent
from app.core import event_bus


def _scripted_director() -> FunctionModel:
    """A streamable director model that calls one real tool, then replies — so the SSE path
    exercises tool events AND text deltas (the default dispatch_mock calls NO tools)."""
    fstate = {"n": 0}

    def fn(messages, info):
        fstate["n"] += 1
        if fstate["n"] == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name="get_project_state", args={})])
        return ModelResponse(parts=[TextPart(content="Here is your project state.")])

    sstate = {"n": 0}

    async def stream_fn(messages, info):
        sstate["n"] += 1
        if sstate["n"] == 1:
            yield {0: DeltaToolCall(name="get_project_state", json_args="{}", tool_call_id="c1")}
        else:
            yield "Here is your project state."

    return FunctionModel(fn, stream_function=stream_fn)


async def _project(client) -> str:
    pid = (await client.post("/api/projects", json={"title": "Stream"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    return pid


async def test_director_stream_emits_tool_events_then_done(client):
    pid = await _project(client)
    body = ""
    with director_agent.override(model=_scripted_director()):
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
    assert "text_delta" in body  # the reply streams as token deltas, not only on `done`
    assert '"type": "done"' in body
    assert "Here is your project state." in body  # the final reply also rides on `done`


async def test_director_stream_persists_the_turn(client):
    pid = await _project(client)
    with director_agent.override(model=_scripted_director()):
        async with client.stream(
            "POST", f"/api/projects/{pid}/director/stream", json={"message": "hello"}
        ) as resp:
            async for _ in resp.aiter_text():
                pass
    turns = (await client.get(f"/api/projects/{pid}/director/turns")).json()
    assert turns[-2]["role"] == "user" and turns[-2]["content"] == "hello"
    assert turns[-1]["role"] == "assistant"


def _scripted_shot_review() -> FunctionModel:
    """Calls get_review on a specific shot, then replies — so tool_start carries a shot ref."""
    fstate = {"n": 0}

    def fn(messages, info):
        fstate["n"] += 1
        if fstate["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="get_review", args={"shot_id": "shot-xyz"})]
            )
        return ModelResponse(parts=[TextPart(content="No take yet.")])

    sstate = {"n": 0}

    async def stream_fn(messages, info):
        sstate["n"] += 1
        if sstate["n"] == 1:
            yield {0: DeltaToolCall(name="get_review", json_args='{"shot_id": "shot-xyz"}', tool_call_id="c1")}
        else:
            yield "No take yet."

    return FunctionModel(fn, stream_function=stream_fn)


async def test_director_stream_carries_shot_ref_for_highlighting(client):
    pid = await _project(client)
    body = ""
    with director_agent.override(model=_scripted_shot_review()):
        async with client.stream(
            "POST", f"/api/projects/{pid}/director/stream", json={"message": "review the shot"}
        ) as resp:
            async for chunk in resp.aiter_text():
                body += chunk
    assert "tool_start" in body
    assert "get_review" in body
    assert "shot-xyz" in body  # the shot ref rides on tool_start so the board can highlight it


async def test_plan_stream_emits_stage_events_then_done_and_persists(client):
    pid = (await client.post("/api/projects", json={"title": "Plan stream"})).json()["id"]
    body = ""
    async with client.stream(
        "POST", f"/api/projects/{pid}/plan/stream", json={"raw_prompt": "a 20s teaser"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for chunk in resp.aiter_text():
            body += chunk
    # all four stages stream, each transitions to done, then one terminal done frame
    for phase in ("brief", "script", "looks", "board"):
        assert f'"phase": "{phase}"' in body
    assert '"status": "done"' in body
    assert '"type": "done"' in body
    # and the plan was persisted atomically (script + storyboard exist afterwards)
    assert len((await client.get(f"/api/projects/{pid}/script")).json()) > 0
    assert len((await client.get(f"/api/projects/{pid}/storyboard")).json()) > 0


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
