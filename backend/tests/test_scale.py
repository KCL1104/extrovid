"""Per-scene storyboard planning + batch scene rendering + view-matched references.

Offline (mock LLM + video). The per-scene fan-out is what breaks the 5-10-shot /
120-second ceiling (docs/vimax-research.md C3/C4/C6).
"""

from app.models.shot import Shot
from app.pipeline.orchestrator import _scene_tail, build_scene_storyboard_prompt
from app.schemas.pipeline import (
    CameraSpec,
    PerformanceSpec,
    SceneBeat,
    SceneDraft,
    ShotDTO,
    VisualBrief,
)
from app.services.prompt_service import portrait_view_for


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


async def test_camera_id_globalized_across_scenes(client):
    """The continuity baton renumbers camera_id globally, so it no longer resets per scene."""
    pid = (await client.post("/api/projects", json={"title": "Cam"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 40s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    by_scene: dict[int, list[int]] = {}
    for s in shots:
        by_scene.setdefault(s["scene_order"], []).append(s["camera_id"])
    assert len(by_scene) >= 2  # multi-scene
    orders = sorted(by_scene)
    for earlier, later in zip(orders, orders[1:], strict=False):
        # a later scene's cameras start past the earlier scene's — no reset to 0, no collision
        assert min(by_scene[later]) > max(by_scene[earlier])


def _scene() -> SceneDraft:
    return SceneDraft(
        order=1,
        title="Reveal",
        summary="the payoff",
        beats=[SceneBeat(order=0, description="hero shot")],
        est_duration_sec=10,
    )


def test_scene_storyboard_prompt_carries_continuity_baton():
    assert "CONTINUITY" not in build_scene_storyboard_prompt(_scene(), None, 10)
    p = build_scene_storyboard_prompt(
        _scene(), None, 10, prev_tail="ended on: a wide street at dusk"
    )
    assert "CONTINUITY" in p
    assert "a wide street at dusk" in p


def _vb(axis_lock: bool) -> VisualBrief:
    return VisualBrief(
        scene_order=1,
        visual_style="noir",
        mood="tense",
        palette=["#111"],
        lighting="hard rim",
        camera_language="locked-off",
        axis_lock=axis_lock,
    )


def test_axis_lock_reaches_scene_prompt():
    assert "180-degree line" in build_scene_storyboard_prompt(_scene(), _vb(True), 10)
    assert "180-degree line" not in build_scene_storyboard_prompt(_scene(), _vb(False), 10)


async def test_screen_direction_persists_through_planning(client):
    pid = (await client.post("/api/projects", json={"title": "SD"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    assert all(s["screen_direction"] for s in shots)  # planner emits it, it round-trips


def test_scene_tail_summarizes_last_shot():
    assert _scene_tail([]) is None
    shot = ShotDTO(
        order=3,
        scene_order=0,
        purpose="exit",
        duration_sec=4,
        beat="b",
        camera_spec=CameraSpec(shot_size="MS", angle="eye-level", movement="static"),
        performance_spec=PerformanceSpec(subject="Maya", action="turns to the door"),
        acceptance_rules=["subject in frame"],
        last_frame_desc="Maya in the doorway, light behind her",
        framing="Maya center, facing the door",
    )
    tail = _scene_tail([shot])
    assert "Maya in the doorway" in tail
    assert "Maya center" in tail


def test_portrait_view_matching():
    assert portrait_view_for(None) == "front"
    assert portrait_view_for(_shot()) == "front"
    assert (
        portrait_view_for(_shot(framing="over-the-shoulder behind Maya, facing the window"))
        == "back"
    )
    walk_away = _shot(first_frame_desc="Maya walking away from camera, back view")
    assert portrait_view_for(walk_away) == "back"
    assert portrait_view_for(_shot(framing="Maya in profile on right third")) == "side"
