"""Long-source import: events -> scenes -> cast. Offline (mock LLM)."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.source_agent import event_agent

SOURCE = (
    "Maya had walked past the old camera shop a hundred times. Today the door stood "
    "open. Inside, the shopkeeper slid a battered film camera across the counter and "
    "said it had been waiting for her. She laughed it off — until the first developed "
    "frame showed a street that no longer existed, and her own face in the crowd."
)


async def test_import_source_builds_events_scenes_and_cast(client):
    pid = (await client.post("/api/projects", json={"title": "Import"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/import-source", json={"text": SOURCE})
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == 2  # mock yields exactly two events (is_last on the second)
    assert body["scenes"] == 2  # one scene per event
    assert "Maya" in body["cast"]

    events = (await client.get(f"/api/projects/{pid}/source-events")).json()
    assert [e["index"] for e in events] == [0, 1]
    assert events[-1]["is_last"] is True
    assert events[0]["process_chain"]

    # the import landed as the project's script with contiguous scene orders
    scenes = (await client.get(f"/api/projects/{pid}/script")).json()
    assert [s["order"] for s in scenes] == [0, 1]
    assert (await client.get(f"/api/projects/{pid}")).json()["status"] == "scripted"


async def test_reimport_is_idempotent_and_replace_clears(client):
    pid = (await client.post("/api/projects", json={"title": "Resume"})).json()["id"]
    await client.post(f"/api/projects/{pid}/import-source", json={"text": SOURCE})
    # second run: extraction resumes past the completed event list (no new events)
    r2 = await client.post(f"/api/projects/{pid}/import-source", json={"text": SOURCE})
    assert r2.json()["events"] == 2
    # replace=True discards progress and re-extracts
    r3 = await client.post(
        f"/api/projects/{pid}/import-source", json={"text": SOURCE, "replace": True}
    )
    assert r3.json()["events"] == 2


async def test_import_source_requires_substantial_text(client):
    pid = (await client.post("/api/projects", json={"title": "Tiny"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/import-source", json={"text": "too short"})
    assert r.status_code == 422


async def test_event_index_echo_validator_retries_then_fails():
    """ViMax's index-echo assert as a ModelRetry: a drifting index is never persisted."""

    def fn(messages, info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name
        wrong = {
            "index": 7,  # expected 0
            "is_last": True,
            "description": "drifted",
            "process_chain": ["x"],
        }
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=wrong)])

    with event_agent.override(model=FunctionModel(fn)):
        with pytest.raises(UnexpectedModelBehavior):
            await event_agent.run("EVENT_INDEX=0\nSource: x", deps=0)


async def test_imported_script_flows_into_the_pipeline(client):
    """The import is a script: visual dev + storyboard run on it unchanged."""
    pid = (await client.post("/api/projects", json={"title": "Flow"})).json()["id"]
    await client.post(f"/api/projects/{pid}/import-source", json={"text": SOURCE})
    scenes = (await client.get(f"/api/projects/{pid}/script")).json()
    script = {
        "logline": "imported",
        "scenes": [
            {
                "order": s["order"],
                "title": s["title"],
                "summary": s["summary"],
                "beats": s["beats"],
                "est_duration_sec": s["est_duration_sec"],
            }
            for s in scenes
        ],
    }
    r = await client.post(f"/api/projects/{pid}/visual-briefs", json=script)
    assert r.status_code == 200
    r2 = await client.post(
        f"/api/projects/{pid}/storyboard",
        json={"script": script, "target_duration_sec": 24},
    )
    assert r2.status_code == 200
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    assert len(shots) >= 2
    assert sorted(s["order"] for s in shots) == list(range(len(shots)))
