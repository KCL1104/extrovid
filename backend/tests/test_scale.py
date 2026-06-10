"""Per-scene storyboard planning + batch scene rendering + view-matched references.

Offline (mock LLM + video). The per-scene fan-out is what breaks the 5-10-shot /
120-second ceiling (docs/vimax-research.md C3/C4/C6).
"""

from app.models.shot import Shot
from app.services.generate_service import _portrait_view_for


async def test_long_brief_is_accepted_and_planned_per_scene(client):
    pid = (await client.post("/api/projects", json={"title": "Long"})).json()["id"]
    r = await client.post(
        f"/api/projects/{pid}/run", json={"raw_prompt": "a 300s brand documentary"}
    )
    assert r.status_code == 200
    result = r.json()
    assert result["brief"]["target_duration_sec"] == 300
    shots = [s for sc in result["storyboard"]["scenes"] for s in sc["shots"]]
    assert len(shots) > 10  # past the old global ceiling
    assert sorted(s["order"] for s in shots) == list(range(len(shots)))
    assert all(0 < s["duration_sec"] <= 15 for s in shots)


async def test_scene_orders_follow_the_script(client):
    pid = (await client.post("/api/projects", json={"title": "Scenes"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 40s teaser"})
    result = r.json()
    script_orders = [s["order"] for s in result["script"]["scenes"]]
    sb_orders = [sc["scene_order"] for sc in result["storyboard"]["scenes"]]
    assert sb_orders == sorted(script_orders)
    for sc in result["storyboard"]["scenes"]:
        assert all(s["scene_order"] == sc["scene_order"] for s in sc["shots"])


async def test_generate_all_for_a_scene(client):
    pid = (await client.post("/api/projects", json={"title": "Batch"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    scene0 = [s for s in shots if s["scene_order"] == 0]

    r = await client.post(f"/api/projects/{pid}/scenes/0/generate-all", json={})
    assert r.status_code == 200
    takes = r.json()
    assert len(takes) == len(scene0)
    assert all(t["job_status"] == "succeeded" for t in takes)  # mock completes instantly


async def test_generate_all_with_continuation_chains(client):
    pid = (await client.post("/api/projects", json={"title": "Chain"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})

    r = await client.post(
        f"/api/projects/{pid}/generate-all", json={"continue_from_previous": True}
    )
    assert r.status_code == 200
    takes = r.json()
    assert len(takes) >= 2
    # the anchor renders directly; every later shot chains on its predecessor
    assert "continues from shot #" not in (takes[0]["routing_note"] or "")
    for t in takes[1:]:
        assert "continues from shot #" in (t["routing_note"] or "")


async def test_generate_all_404s_without_storyboard(client):
    pid = (await client.post("/api/projects", json={"title": "Empty"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/generate-all", json={})
    assert r.status_code == 404


def _shot(**kw) -> Shot:
    base = dict(
        project_id="p", order=0, scene_order=0, purpose="x", duration_sec=4, beat="b"
    )
    base.update(kw)
    return Shot(**base)


def test_portrait_view_matching():
    assert _portrait_view_for(None) == "front"
    assert _portrait_view_for(_shot()) == "front"
    assert (
        _portrait_view_for(_shot(framing="over-the-shoulder behind Maya, facing the window"))
        == "back"
    )
    assert _portrait_view_for(_shot(first_frame_desc="Maya walking away from camera, back view")) == "back"
    assert _portrait_view_for(_shot(framing="Maya in profile on right third")) == "side"
