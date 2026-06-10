"""Project state snapshot + targeted revision/staleness + DirectorAgent. Offline."""

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.director_agent import director_agent


async def _project(client, prompt="a 20s teaser"):
    pid = (await client.post("/api/projects", json={"title": "Dir"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": prompt})
    return pid


# --------------------------------------------------------------------------- #
# D1 — snapshot + dependency gating
# --------------------------------------------------------------------------- #


async def test_state_snapshot_shape(client):
    pid = await _project(client)
    r = await client.get(f"/api/projects/{pid}/state")
    assert r.status_code == 200
    s = r.json()
    assert s["has_brief"] is True
    assert s["scenes"] >= 1
    assert s["shots"] >= 2
    assert s["stale_shots"] == 0
    assert s["shots_with_take"] == 0
    assert any(c["name"] == "Maya" for c in s["characters"])


async def test_rough_cut_gated_on_missing_takes(client):
    pid = await _project(client)
    r = await client.post(f"/api/projects/{pid}/rough-cut", json={})
    assert r.status_code == 422
    assert "finished takes" in str(r.json()["detail"]["missing"])


# --------------------------------------------------------------------------- #
# D2 — targeted revision + staleness cascade
# --------------------------------------------------------------------------- #


async def test_revise_scene_cascades_staleness(client):
    pid = await _project(client)
    scenes = (await client.get(f"/api/projects/{pid}/script")).json()
    sid = scenes[0]["id"]
    r = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"scene:{sid}", "instruction": "make the hook moodier"},
    )
    assert r.status_code == 200
    assert "(revised)" in r.json()["revised"]["title"]

    # the revised scene is fresh; its downstream shots are now stale
    state = (await client.get(f"/api/projects/{pid}/state")).json()
    assert state["stale_shots"] >= 1
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    scene0_shots = [s for s in shots if s["scene_order"] == scenes[0]["order"]]
    assert all(s["stale"] for s in scene0_shots)
    other_shots = [s for s in shots if s["scene_order"] != scenes[0]["order"]]
    assert all(not s["stale"] for s in other_shots)


async def test_revise_shot_in_place(client):
    pid = await _project(client)
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    r = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"shot:{shots[0]['id']}", "instruction": "make it a close-up"},
    )
    assert r.status_code == 200
    assert "(revised)" in r.json()["revised"]["purpose"]


async def test_revise_rejects_bad_targets(client):
    pid = await _project(client)
    r = await client.post(
        f"/api/projects/{pid}/revise", json={"target": "nonsense", "instruction": "x"}
    )
    assert r.status_code == 422
    r2 = await client.post(
        f"/api/projects/{pid}/revise", json={"target": "shot:no-such-id", "instruction": "x"}
    )
    assert r2.status_code == 404


async def test_new_brief_marks_everything_stale(client):
    pid = await _project(client)
    await client.post(f"/api/projects/{pid}/brief", json={"raw_prompt": "a different idea"})
    state = (await client.get(f"/api/projects/{pid}/state")).json()
    assert state["stale_scenes"] >= 1
    assert state["stale_shots"] >= 1


# --------------------------------------------------------------------------- #
# D3 — DirectorAgent
# --------------------------------------------------------------------------- #


async def test_director_turn_with_tool_call(client):
    pid = await _project(client)
    calls = {"n": 0}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="get_project_state", args={})]
            )
        return ModelResponse(
            parts=[TextPart(content="Planning is complete — shall we render scene 0?")]
        )

    with director_agent.override(model=FunctionModel(fn)):
        r = await client.post(
            f"/api/projects/{pid}/director", json={"message": "where are we?"}
        )
    assert r.status_code == 200
    body = r.json()
    assert "Planning is complete" in body["reply"]
    assert body["actions"][0]["tool"] == "get_project_state"
    assert body["state"]["shots"] >= 2


async def test_director_generates_a_shot_via_tool(client):
    pid = await _project(client)
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    calls = {"n": 0}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="generate_shot", args={"shot_id": shots[0]["id"]})]
            )
        return ModelResponse(parts=[TextPart(content="Submitted one take for shot 0.")])

    with director_agent.override(model=FunctionModel(fn)):
        r = await client.post(f"/api/projects/{pid}/director", json={"message": "render shot 0"})
    assert r.status_code == 200
    assert r.json()["actions"][0]["tool"] == "generate_shot"
    assert r.json()["state"]["shots_with_take"] >= 1


async def test_director_history_persists_across_turns(client):
    pid = await _project(client)

    def fn(messages, info: AgentInfo) -> ModelResponse:
        from app.providers.mock_data import _user_text

        seen = "SECRET-MARKER" in _user_text(messages)
        return ModelResponse(parts=[TextPart(content=f"seen={seen}")])

    with director_agent.override(model=FunctionModel(fn)):
        await client.post(
            f"/api/projects/{pid}/director", json={"message": "remember SECRET-MARKER"}
        )
        r2 = await client.post(f"/api/projects/{pid}/director", json={"message": "recall it"})
    # the second turn's prompt carried the first turn's text history
    assert r2.json()["reply"] == "seen=True"
