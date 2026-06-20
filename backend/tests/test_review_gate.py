"""Review gate (P1): tier-aware approval gating, lock, annotations, propose-diff, cost."""


async def _plan(client, raw_prompt: str) -> str:
    pid = (await client.post("/api/projects", json={"title": "RG"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": raw_prompt})
    assert r.status_code == 200
    return pid


async def test_short_is_not_gated(client):
    """SHORT keeps one-prompt-to-video: generation runs without an approval step."""
    pid = await _plan(client, "a 20s teaser")
    state = (await client.get(f"/api/projects/{pid}/state")).json()
    assert state["tier"] == "short"
    assert state["gated"] is False
    r = await client.post(f"/api/projects/{pid}/generate-all", json={})
    assert r.status_code == 200  # no approval needed


async def test_medium_is_gated_until_approved(client):
    pid = await _plan(client, "a 180s explainer video")
    state = (await client.get(f"/api/projects/{pid}/state")).json()
    assert state["tier"] == "medium"
    assert state["gated"] is True
    assert state["project_status"] == "storyboarded"

    # generation is blocked before approval
    blocked = await client.post(f"/api/projects/{pid}/generate-all", json={})
    assert blocked.status_code == 409
    assert "approved" in blocked.json()["detail"]

    # approve the whole plan -> APPROVED -> the gate opens
    appr = await client.post(f"/api/projects/{pid}/plan/approve", json={})
    assert appr.status_code == 200
    assert appr.json()["approved"] is True
    assert (await client.get(f"/api/projects/{pid}/state")).json()["project_status"] == "approved"
    # one scene is under the per-user video cap, so the gate-opened path renders (200);
    # the whole plan can exceed the daily cap, which is an orthogonal guardrail.
    ok = await client.post(f"/api/projects/{pid}/scenes/0/generate-all", json={})
    assert ok.status_code == 200


async def test_revising_after_approval_re_gates(client):
    """Editing the plan after sign-off invalidates it — generation re-locks until re-approved."""
    pid = await _plan(client, "a 180s explainer video")
    await client.post(f"/api/projects/{pid}/plan/approve", json={})
    assert (await client.get(f"/api/projects/{pid}/state")).json()["project_status"] == "approved"

    shot = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]
    r = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"shot:{shot['id']}", "instruction": "make it wider"},
    )
    assert r.status_code == 200
    assert (await client.get(f"/api/projects/{pid}/state")).json()["project_status"] == "storyboarded"
    blocked = await client.post(f"/api/projects/{pid}/scenes/0/generate-all", json={})
    assert blocked.status_code == 409


async def test_revising_visual_brief_after_approval_re_gates(client):
    """A brief edit changes what renders, so it must also invalidate the sign-off."""
    pid = await _plan(client, "a 180s explainer video")
    s0 = next(
        s for s in (await client.get(f"/api/projects/{pid}/script")).json() if s["order"] == 0
    )
    await client.post(f"/api/projects/{pid}/plan/approve", json={})
    assert (await client.get(f"/api/projects/{pid}/state")).json()["project_status"] == "approved"

    r = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"visual_brief:{s0['id']}", "instruction": "warmer palette"},
    )
    assert r.status_code == 200
    assert (await client.get(f"/api/projects/{pid}/state")).json()["project_status"] == "storyboarded"
    blocked = await client.post(f"/api/projects/{pid}/scenes/0/generate-all", json={})
    assert blocked.status_code == 409


async def test_annotation_rejects_foreign_target(client):
    """An anchor must belong to the path project — no cross-project / dangling anchors."""
    pid_a = await _plan(client, "a 20s teaser")
    shot_a = (await client.get(f"/api/projects/{pid_a}/storyboard")).json()[0]
    pid_b = (await client.post("/api/projects", json={"title": "B"})).json()["id"]
    bad = await client.post(
        f"/api/projects/{pid_b}/annotations",
        json={"target_kind": "shot", "target_id": shot_a["id"], "intent": "comment", "text": "x"},
    )
    assert bad.status_code == 404


async def test_plan_cost_estimate(client):
    pid = await _plan(client, "a 180s explainer video")
    cost = (await client.get(f"/api/projects/{pid}/plan/cost")).json()
    assert cost["shots"] > 0
    assert cost["total_usd"] > 0
    assert cost["total_usd"] >= cost["video_usd"]


async def test_partial_scene_approval_gates_per_scene(client):
    pid = await _plan(client, "a 180s explainer video")
    scenes = (await client.get(f"/api/projects/{pid}/script")).json()
    s0 = next(s for s in scenes if s["order"] == 0)

    # approve only scene 0
    appr = await client.post(f"/api/projects/{pid}/plan/approve", json={"scene_ids": [s0["id"]]})
    assert appr.status_code == 200
    assert appr.json()["approved"] is False  # not every scene approved -> project still gated

    # scene 0 may render; scene 1 may not
    ok = await client.post(f"/api/projects/{pid}/scenes/0/generate-all", json={})
    assert ok.status_code == 200
    blocked = await client.post(f"/api/projects/{pid}/scenes/1/generate-all", json={})
    assert blocked.status_code == 409


async def test_lock_blocks_revision(client):
    pid = await _plan(client, "a 20s teaser")
    shot = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]

    lock = await client.post(f"/api/projects/{pid}/shots/{shot['id']}/lock", json={"locked": True})
    assert lock.status_code == 200 and lock.json()["locked"] is True

    blocked = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"shot:{shot['id']}", "instruction": "make it wider"},
    )
    assert blocked.status_code == 422
    assert "locked" in blocked.json()["detail"]

    await client.post(f"/api/projects/{pid}/shots/{shot['id']}/lock", json={"locked": False})
    ok = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"shot:{shot['id']}", "instruction": "make it wider"},
    )
    assert ok.status_code == 200


async def test_revise_dry_run_is_non_destructive(client):
    pid = await _plan(client, "a 20s teaser")
    scenes = (await client.get(f"/api/projects/{pid}/script")).json()
    s0 = next(s for s in scenes if s["order"] == 0)
    before_title = s0["title"]

    proposal = await client.post(
        f"/api/projects/{pid}/revise",
        json={"target": f"scene:{s0['id']}", "instruction": "moodier", "dry_run": True},
    )
    assert proposal.status_code == 200
    body = proposal.json()
    assert body["dry_run"] is True
    assert body["kind"] == "scene"
    assert body["instruction"] == "moodier"  # echoed back so the proposal is self-describing
    assert body["before"]["title"] == before_title
    assert body["after"]["title"] != before_title

    # the stored scene is untouched by the dry run
    still = (await client.get(f"/api/projects/{pid}/script")).json()
    assert next(s for s in still if s["order"] == 0)["title"] == before_title


async def test_revise_apply_commits_exact_proposal(client):
    """Accepting a proposal writes its exact `after` — no second, possibly-different run."""
    pid = await _plan(client, "a 20s teaser")
    scenes = (await client.get(f"/api/projects/{pid}/script")).json()
    s0 = next(s for s in scenes if s["order"] == 0)

    proposal = (
        await client.post(
            f"/api/projects/{pid}/revise",
            json={"target": f"scene:{s0['id']}", "instruction": "moodier", "dry_run": True},
        )
    ).json()
    after = proposal["after"]

    applied = await client.post(
        f"/api/projects/{pid}/revise/apply",
        json={"target": f"scene:{s0['id']}", "after": after},
    )
    assert applied.status_code == 200

    stored = next(
        s for s in (await client.get(f"/api/projects/{pid}/script")).json() if s["order"] == 0
    )
    assert stored["title"] == after["title"]
    assert stored["summary"] == after["summary"]


async def test_revise_apply_refuses_locked(client):
    pid = await _plan(client, "a 20s teaser")
    shot = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]
    await client.post(f"/api/projects/{pid}/shots/{shot['id']}/lock", json={"locked": True})
    blocked = await client.post(
        f"/api/projects/{pid}/revise/apply",
        json={"target": f"shot:{shot['id']}", "after": {"purpose": "x"}},
    )
    assert blocked.status_code == 422


async def test_annotation_crud_and_resolve(client):
    pid = await _plan(client, "a 20s teaser")
    shot = (await client.get(f"/api/projects/{pid}/storyboard")).json()[0]

    created = await client.post(
        f"/api/projects/{pid}/annotations",
        json={
            "target_kind": "shot",
            "target_id": shot["id"],
            "field": "framing",
            "intent": "change",
            "text": "push in closer on the product",
        },
    )
    assert created.status_code == 200
    ann_id = created.json()["id"]
    assert created.json()["status"] == "open"

    listed = (await client.get(f"/api/projects/{pid}/annotations")).json()
    assert any(a["id"] == ann_id for a in listed)

    resolved = await client.post(f"/api/projects/{pid}/annotations/{ann_id}/resolve")
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"


async def test_plan_annotation_requires_no_target_but_others_do(client):
    pid = await _plan(client, "a 20s teaser")
    # a scene annotation without target_id is rejected at the schema
    bad = await client.post(
        f"/api/projects/{pid}/annotations",
        json={"target_kind": "scene", "intent": "comment", "text": "x"},
    )
    assert bad.status_code == 422
    # a plan-level note needs no target
    ok = await client.post(
        f"/api/projects/{pid}/annotations",
        json={"target_kind": "plan", "intent": "comment", "text": "overall pacing feels slow"},
    )
    assert ok.status_code == 200
