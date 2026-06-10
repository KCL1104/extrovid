"""PATCH /projects/{pid}/shots/{shot_id} — per-shot detailed direction.

Covers the partial-update semantics, ownership/cast validation, the director's-notes and
transition ending-hint prompt composition, and the generate fallback to shot.character_id.
All offline (mock LLM + mock video)."""

from app.models.shot import Shot
from app.services.prompt_service import compose_shot_prompt

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


async def _project_with_shots(client):
    pid = (await client.post("/api/projects", json={"title": "Direction"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    shots = (await client.get(f"/api/projects/{pid}/storyboard")).json()
    return pid, shots


async def _make_character(client, pid: str, name: str, frame_index: int = 0) -> str:
    """Promote a generated concept frame to a CharacterProfile; returns its id."""
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]
    await client.post(f"/api/projects/{pid}/concept-sets/{cs['id']}/generate-images")
    frame = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["look_frames"][
        frame_index
    ]
    await client.post(
        f"/api/projects/{pid}/look-frames/{frame['id']}/promote",
        json={"target": "character_ref", "name": name},
    )
    chars = (await client.get(f"/api/projects/{pid}/characters")).json()
    return next(c["id"] for c in chars if c["name"] == name)


def _shot(**overrides) -> Shot:
    base = dict(
        project_id="p",
        order=0,
        scene_order=0,
        purpose="reveal the product",
        duration_sec=4,
        beat="hero moment",
        camera_spec={"shot_size": "CU", "angle": "low", "movement": "dolly-in"},
        performance_spec={"subject": "the watch", "action": "rotates slowly"},
    )
    base.update(overrides)
    return Shot(**base)


# --------------------------------------------------------------------------- #
# PATCH happy path + partial semantics
# --------------------------------------------------------------------------- #


async def test_patch_shot_happy_path(client):
    pid, shots = await _project_with_shots(client)
    sid = shots[0]["id"]
    patch = {
        "purpose": "open on the hero product",
        "beat": "rewritten beat",
        "duration_sec": 6.5,
        "camera_spec": {"shot_size": "ECU", "angle": "low", "movement": "dolly-in", "lens": "35mm"},
        "performance_spec": {"subject": "the watch", "action": "rotates slowly", "emotion": "calm"},
        "transition": "match_cut",
        "acceptance_rules": ["subject centered", "logo readable"],
        "extra_direction": "rain streaks on the window, neon reflections",
    }
    r = await client.patch(f"/api/projects/{pid}/shots/{sid}", json=patch)
    assert r.status_code == 200
    body = r.json()
    assert body["purpose"] == "open on the hero product"
    assert body["beat"] == "rewritten beat"
    assert body["duration_sec"] == 6.5
    assert body["camera_spec"] == patch["camera_spec"]
    assert body["performance_spec"] == patch["performance_spec"]
    assert body["transition"] == "match_cut"
    assert body["acceptance_rules"] == ["subject centered", "logo readable"]
    assert body["extra_direction"] == "rain streaks on the window, neon reflections"
    assert body["character_id"] is None

    # persisted — the storyboard read returns the edited shot
    stored = next(
        s for s in (await client.get(f"/api/projects/{pid}/storyboard")).json() if s["id"] == sid
    )
    assert stored["transition"] == "match_cut"
    assert stored["extra_direction"] == "rain streaks on the window, neon reflections"
    assert stored["camera_spec"]["lens"] == "35mm"


async def test_patch_shot_partial_leaves_other_fields(client):
    pid, shots = await _project_with_shots(client)
    before = shots[0]
    r = await client.patch(
        f"/api/projects/{pid}/shots/{before['id']}", json={"extra_direction": "slow burn"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["extra_direction"] == "slow burn"
    assert body["purpose"] == before["purpose"]
    assert body["beat"] == before["beat"]
    assert body["camera_spec"] == before["camera_spec"]
    assert body["duration_sec"] == before["duration_sec"]


async def test_patch_shot_validation_422(client):
    pid, shots = await _project_with_shots(client)
    sid = shots[0]["id"]
    assert (
        await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"duration_sec": 20})
    ).status_code == 422  # > 15s
    assert (
        await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"transition": "wipe"})
    ).status_code == 422  # not a ShotTransition
    assert (
        await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"acceptance_rules": []})
    ).status_code == 422  # min 1 rule when provided
    # explicit null on a non-nullable column would persist and brick storyboard reads
    assert (
        await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"camera_spec": None})
    ).status_code == 422
    assert (
        await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"purpose": None})
    ).status_code == 422
    # the truly nullable fields may still be cleared explicitly
    assert (
        await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"extra_direction": None})
    ).status_code == 200


# --------------------------------------------------------------------------- #
# ownership + cast validation
# --------------------------------------------------------------------------- #


async def test_patch_shot_404_for_foreign_or_missing_shot(client):
    pid_a, shots_a = await _project_with_shots(client)
    pid_b = (await client.post("/api/projects", json={"title": "Other"})).json()["id"]
    r = await client.patch(
        f"/api/projects/{pid_b}/shots/{shots_a[0]['id']}", json={"purpose": "x"}
    )
    assert r.status_code == 404  # shot belongs to another project
    r2 = await client.patch(f"/api/projects/{pid_a}/shots/no-such-shot", json={"purpose": "x"})
    assert r2.status_code == 404


async def test_patch_shot_character_validation(client):
    pid, shots = await _project_with_shots(client)
    sid = shots[0]["id"]

    # unknown character id
    r = await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"character_id": "ghost"})
    assert r.status_code == 404

    # a character that belongs to ANOTHER project is rejected
    other_pid, _ = await _project_with_shots(client)
    foreign_char = await _make_character(client, other_pid, "Stranger")
    r = await client.patch(
        f"/api/projects/{pid}/shots/{sid}", json={"character_id": foreign_char}
    )
    assert r.status_code == 404

    # own character persists; explicit null clears the cast lock
    own_char = await _make_character(client, pid, "Hero")
    r = await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"character_id": own_char})
    assert r.status_code == 200
    assert r.json()["character_id"] == own_char
    r = await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"character_id": None})
    assert r.status_code == 200
    assert r.json()["character_id"] is None


# --------------------------------------------------------------------------- #
# prompt composition — director's notes + transition ending hint
# --------------------------------------------------------------------------- #


def test_prompt_includes_directors_notes_near_action():
    p = compose_shot_prompt(_shot(extra_direction="rain on the window, neon glow"))
    assert "Director's notes: rain on the window, neon glow" in p
    # high priority: the notes land before the camera segment, next to the action
    assert p.index("Director's notes") < p.index("camera:")


def test_prompt_transition_ending_hints():
    p = compose_shot_prompt(_shot(transition="match_cut"))
    assert "match the next shot's opening" in p
    for t in ("dissolve", "fade"):
        assert "settle gently" in compose_shot_prompt(_shot(transition=t))
    for t in ("cut", "none"):
        assert "ending:" not in compose_shot_prompt(_shot(transition=t))


def test_prompt_without_notes_unchanged():
    p = compose_shot_prompt(_shot())
    assert "Director's notes" not in p
    assert "ending:" not in p  # default transition is cut


# --------------------------------------------------------------------------- #
# generate fallback — shot.character_id is the default cast
# --------------------------------------------------------------------------- #


async def test_generate_falls_back_to_shot_character(client):
    pid, shots = await _project_with_shots(client)
    char_id = await _make_character(client, pid, "Hero")
    sid = shots[0]["id"]
    await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"character_id": char_id})

    # no character in the request -> the shot's cast lock kicks in -> r2v with refs
    v = (await client.post(f"/api/projects/{pid}/shots/{sid}/generate", json={})).json()
    assert "r2v" in (v["model"] or "")
    assert "featuring Hero" in (v["prompt"] or "")

    # a shot WITHOUT a cast lock still routes without references
    sid2 = shots[1]["id"]
    v2 = (await client.post(f"/api/projects/{pid}/shots/{sid2}/generate", json={})).json()
    assert "r2v" not in (v2["model"] or "")


async def test_generate_explicit_character_wins_over_shot_default(client):
    pid, shots = await _project_with_shots(client)
    hero = await _make_character(client, pid, "Hero", frame_index=0)
    rival = await _make_character(client, pid, "Rival", frame_index=1)
    sid = shots[0]["id"]
    await client.patch(f"/api/projects/{pid}/shots/{sid}", json={"character_id": hero})

    v = (
        await client.post(
            f"/api/projects/{pid}/shots/{sid}/generate", json={"character_id": rival}
        )
    ).json()
    assert "featuring Rival" in (v["prompt"] or "")
    assert "featuring Hero" not in (v["prompt"] or "")
