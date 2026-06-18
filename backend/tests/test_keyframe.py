"""Keyframe contract + per-shot keyframe generation. Offline (mock LLM + images + video)."""

from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.services.imagegen_service import _keyframe_edit_instruction
from app.services.prompt_service import (
    compose_keyframe_prompt,
    compose_shot_prompt,
    portrait_view_for,
)


def _bare_shot(**overrides) -> Shot:
    base = dict(
        project_id="p", order=0, scene_order=0, purpose="x", duration_sec=4, beat="b"
    )
    return Shot(**{**base, **overrides})


def test_portrait_view_matches_shot_direction():
    front = _bare_shot(performance_spec={"subject": "Mia", "action": "smiles at camera"})
    assert portrait_view_for(front) == "front"
    back = _bare_shot(
        performance_spec={"subject": "Mia", "action": "leaves the room"},
        framing="Mia centered, back to camera",
    )
    assert portrait_view_for(back) == "back"
    side = _bare_shot(performance_spec={"subject": "Mia", "action": "stands in profile"})
    assert portrait_view_for(side) == "side"
    assert portrait_view_for(None) == "front"


def test_keyframe_edit_instruction_drops_face_for_back_view():
    back = _keyframe_edit_instruction("back", "PROMPT")
    assert "face is not visible" in back
    assert "identity" not in back  # a from-behind shot is never anchored to a front face
    assert "PROMPT" in back
    side = _keyframe_edit_instruction("side", "PROMPT")
    assert "profile" in side
    front = _keyframe_edit_instruction("front", "PROMPT")
    assert "identity" in front


async def _project(client):
    pid = (await client.post("/api/projects", json={"title": "KF"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, shots


async def test_storyboard_carries_the_keyframe_contract(client):
    _, shots = await _project(client)
    s = shots[0]
    assert s["first_frame_desc"]
    assert s["last_frame_desc"]
    assert s["motion_desc"]
    assert s["variation_type"] in ("small", "medium", "large")


def test_motion_desc_drives_the_video_prompt():
    shot = Shot(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal",
        duration_sec=4,
        beat="b",
        performance_spec={"subject": "the watch", "action": "rotates"},
        motion_desc="slow push-in as the watch (silver, black dial) rotates a quarter turn",
        last_frame_desc="the watch face fills the frame, dial readable",
    )
    p = compose_shot_prompt(shot)
    assert "slow push-in as the watch (silver, black dial)" in p
    assert "ending state: the watch face fills the frame" in p
    assert "the watch rotates" not in p  # motion_desc replaces the generic action line


def test_keyframe_prompt_is_a_static_snapshot():
    shot = Shot(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal",
        duration_sec=4,
        beat="b",
        camera_spec={"shot_size": "CU", "angle": "low"},
        performance_spec={"subject": "the watch", "action": "rotates"},
        first_frame_desc="the watch rests on dark slate, crown facing camera",
    )
    ch = CharacterProfile(project_id="p", name="Mia", description="red coat")
    p = compose_keyframe_prompt(
        shot, visual_brief={"visual_style": "noir", "lighting": "hard rim"}, character=ch
    )
    assert "the watch rests on dark slate" in p
    assert "the character is Mia: red coat" in p
    assert "camera: CU low" in p
    assert "no motion blur" in p


async def test_keyframe_endpoint_generates_and_routes(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    r = await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")
    assert r.status_code == 200
    frame = r.json()
    assert frame["image_asset_id"]

    shot = next(
        s for s in (await client.get(f"/api/projects/{pid}/storyboard")).json() if s["id"] == sid
    )
    assert shot["keyframe_frame_id"] == frame["id"]

    # generation prefers the keyframe as the first-frame seed
    v = (await client.post(f"/api/projects/{pid}/shots/{sid}/generate", json={})).json()
    assert "planned keyframe anchors composition" in v["routing_note"]

    # the keyframe is a LookFrame: the refine loop works on it for free
    r2 = await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/refine",
        json={"instruction": "warmer light"},
    )
    assert r2.status_code == 200


async def test_generate_all_keyframes_skips_existing(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    kf = (await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")).json()
    r = await client.post(f"/api/projects/{pid}/storyboard/keyframes")
    assert r.status_code == 200
    after = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    # every shot now has an opening keyframe; the pre-generated one was NOT regenerated
    assert all(s["keyframe_frame_id"] for s in after)
    assert next(s for s in after if s["id"] == sid)["keyframe_frame_id"] == kf["id"]
    # every non-final shot also got a closing keyframe (the continuity seed for chaining)
    final = max(s["order"] for s in after)
    assert all(s["last_keyframe_frame_id"] for s in after if s["order"] < final)


def test_last_keyframe_prompt_uses_the_closing_frame():
    shot = Shot(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal",
        duration_sec=4,
        beat="b",
        first_frame_desc="the watch rests on dark slate, crown facing camera",
        last_frame_desc="the watch face fills the frame, dial readable",
    )
    p = compose_keyframe_prompt(shot, kind="last")
    assert "the watch face fills the frame" in p
    assert "the watch rests on dark slate" not in p  # closing desc, not opening
    assert "no motion blur" in p


async def test_continuation_prefers_planned_last_keyframe(client):
    pid, shots = await _project(client)
    await client.post(f"/api/projects/{pid}/storyboard/keyframes")  # opening + closing frames
    # shot 1 continues from shot 0 seeded by shot 0's PLANNED closing keyframe — no render needed
    v = (
        await client.post(
            f"/api/projects/{pid}/shots/{shots[1]['id']}/generate",
            json={"continue_from_previous": True},
        )
    ).json()
    assert "planned last keyframe" in v["routing_note"]
    assert v["model"].endswith("i2v")


async def test_keyframe_carries_a_gate_verdict(client):
    """Every generated keyframe is reviewed (identity/composition/view) before video spend."""
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    frame = (await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")).json()
    assert frame["score"] is not None and 0 <= frame["score"] <= 10
    assert frame["review"]["verdict"] in ("pass", "revise")
    # the verdict is surfaced on the storyboard so the board can flag it before "Render all"
    shot = next(
        s for s in (await client.get(f"/api/projects/{pid}/storyboard")).json() if s["id"] == sid
    )
    assert shot["keyframe_verdict"] == frame["review"]["verdict"]
    assert shot["keyframe_score"] == frame["score"]


async def test_keyframe_gate_flags_revise(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    # director's notes feed the keyframe review prompt; REVIEW_FORCE pins the mock verdict
    await client.patch(
        f"/api/projects/{pid}/shots/{sid}", json={"extra_direction": "REVIEW_FORCE=revise"}
    )
    frame = (await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")).json()
    assert frame["review"]["verdict"] == "revise"
    assert frame["score"] < 6


async def test_manual_keyframe_review_endpoint(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")
    r = await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe/review")
    assert r.status_code == 200
    assert r.json()["review"]["verdict"] == "pass"


async def test_keyframe_review_404_without_keyframe(client):
    pid, shots = await _project(client)
    r = await client.post(f"/api/projects/{pid}/shots/{shots[0]['id']}/keyframe/review")
    assert r.status_code == 404


async def test_delete_project_with_keyframe(client):
    """delete_project must remove keyframe LookFrames (concept_set_id=None) — else they
    orphan and the project delete violates lookframe_project_id_fkey on Postgres (the prod
    bug). Regression."""
    pid, shots = await _project(client)
    await client.post(f"/api/projects/{pid}/shots/{shots[0]['id']}/keyframe")
    # a DirectorTurn row, to cover that FK path too
    await client.post(f"/api/projects/{pid}/director", json={"message": "status?"})
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404


async def test_explicit_first_frame_beats_keyframe(client):
    pid, shots = await _project(client)
    sid = shots[0]["id"]
    kf = (await client.post(f"/api/projects/{pid}/shots/{sid}/keyframe")).json()
    # an explicit first_frame_asset_id wins over the planned keyframe
    v = (
        await client.post(
            f"/api/projects/{pid}/shots/{sid}/generate",
            json={"first_frame_asset_id": kf["image_asset_id"]},
        )
    ).json()
    assert "planned keyframe" not in v["routing_note"]
    assert v["routing_note"].startswith("i2v")
