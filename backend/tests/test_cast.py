"""Cast pipeline — CastAgent extraction, upsert, auto cast-lock, portrait sheets.

All offline (mock LLM + mock images).
"""

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.cast_agent import cast_agent
from app.agents.storyboard_agent import scene_storyboard_agent
from app.providers.mock_data import _scene_storyboard_dict, _user_text


async def test_run_pipeline_extracts_and_persists_cast(client):
    pid = (await client.post("/api/projects", json={"title": "Cast"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s hero story"})
    assert r.status_code == 200
    body = r.json()
    assert body["cast"], "pipeline result carries the extracted cast"
    assert body["cast"][0]["name"] == "Maya"

    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    assert any(c["name"] == "Maya" for c in chars)
    maya = next(c for c in chars if c["name"] == "Maya")
    assert "black hair" in (maya["description"] or "")
    assert maya["wardrobe_rules"], "dynamic features land in wardrobe_rules"


async def test_cast_generate_endpoint_upserts_by_name(client):
    pid = (await client.post("/api/projects", json={"title": "Upsert"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s hero story"})
    before = (await client.get(f"/api/projects/{pid}/characters")).json()

    r = await client.post(f"/api/projects/{pid}/cast/generate")
    assert r.status_code == 200
    after = (await client.get(f"/api/projects/{pid}/characters")).json()
    # same canonical name -> updated in place, not duplicated
    assert len([c for c in after if c["name"] == "Maya"]) == 1
    assert len(after) == len(before)


async def test_cast_generate_requires_script(client):
    pid = (await client.post("/api/projects", json={"title": "NoScript"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/cast/generate")
    assert r.status_code == 422


async def test_storyboard_character_name_auto_cast_locks(client):
    """A storyboard shot carrying character_name gets its character_id resolved."""
    pid = (await client.post("/api/projects", json={"title": "Lock"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s hero story"})

    def fn(messages, info: AgentInfo) -> ModelResponse:
        args = _scene_storyboard_dict(_user_text(messages))
        args["shots"][0]["character_name"] = "Maya"  # exact cast name
        args["shots"][1]["character_name"] = "Nobody Known"  # no match -> null
        name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])

    script = (await client.get(f"/api/projects/{pid}/script")).json()
    with scene_storyboard_agent.override(model=FunctionModel(fn)):
        r = await client.post(
            f"/api/projects/{pid}/storyboard",
            json={
                "script": {
                    "logline": "L",
                    "scenes": [
                        {
                            "order": s["order"],
                            "title": s["title"],
                            "summary": s["summary"],
                            "beats": s["beats"],
                            "est_duration_sec": s["est_duration_sec"],
                        }
                        for s in script
                    ],
                },
                "target_duration_sec": 20,
            },
        )
    assert r.status_code == 200

    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    maya_id = next(c["id"] for c in chars if c["name"] == "Maya")
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    assert shots[0]["character_id"] == maya_id
    assert shots[1]["character_id"] is None


async def test_portrait_sheet_generation_and_r2v_anchor(client):
    pid = (await client.post("/api/projects", json={"title": "Portraits"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s hero story"})
    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    cid = next(c["id"] for c in chars if c["name"] == "Maya")

    r = await client.post(f"/api/projects/{pid}/characters/{cid}/portraits")
    assert r.status_code == 200
    body = r.json()
    assert set(body["portrait_image_urls"]) == {"front", "side", "back"}

    # the portrait sheet anchors generation: a cast-locked shot routes to r2v
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    sid = shots[0]["id"]
    r2 = await client.post(
        f"/api/projects/{pid}/shots/{sid}/generate", json={"character_id": cid}
    )
    assert r2.status_code == 200
    v = r2.json()
    assert "r2v" in (v["model"] or "")
    # ONE portrait view (matched to the shot's direction) anchors identity
    assert "1 reference image(s)" in v["routing_note"]


async def test_portraits_404_on_unknown_character(client):
    pid = (await client.post("/api/projects", json={"title": "P404"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/characters/nope/portraits")
    assert r.status_code == 404


async def test_cast_agent_force_empty_marker():
    out = (await cast_agent.run("script CAST_FORCE_EMPTY")).output
    assert out.characters == []


async def test_cast_agent_unique_name_validation():
    def fn(messages, info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name
        dup = {
            "characters": [
                {"name": "Mia", "static_features": "a", "dynamic_features": "b"},
                {"name": "mia", "static_features": "c", "dynamic_features": "d"},
            ]
        }
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=dup)])

    import pytest
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    with cast_agent.override(model=FunctionModel(fn)):
        with pytest.raises(UnexpectedModelBehavior):
            await cast_agent.run("anything")
