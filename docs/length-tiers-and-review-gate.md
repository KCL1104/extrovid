# Length tiers + plan review/annotate gate — implementation spec

> Status (2026-06-20): **P0 DONE** (cd4848b) · **P1 DONE** (2b8b5b7 backend, 7ff8d74 frontend) ·
> **P2 DONE** (7952013 — continuity bible + non-destructive diff "apply exact proposal" +
> demote-on-revise re-gating; **still-vs-motion moved to P3** — its cut-side freeze-frame
> rendering belongs with the cut/cost work there). Full backend suite + tsc + eslint + next
> build all green. **P3a DONE** (36284fa — caps→~20min: MAX_TOTAL_SHOTS 160 / MAX_SCENES 40 /
> target_duration le 1200; per-project budget gate). **P3b NEXT** (LONG chapter/act layer +
> outline-first review gate), then **P3c** (still-vs-motion render). Design locked via research
> workflow `wf_1c125d7d`. Companion memory: `extrovid-length-review-plan`.
> NOTE: the backend test suite runs against a REMOTE Railway Postgres by default
> (`TEST_DATABASE_URL`); run locally with `TEST_DATABASE_URL="" pytest` to use fast in-memory
> sqlite and avoid cross-run deadlocks.

## 0. Thesis — two asks, one product story

Fully-unattended generation **collapses as length grows**: continuity drifts, the narrative
arc falls apart, and cost scales linearly (≈ **$6** for a 30s short vs **$90+** for an 80-shot
long piece at N=1, before images/TTS/best-of-N). So the longer the target, the more a **human
review gate** is required — both to catch drift the agents can't self-correct and to avoid
expensive wrong renders. Every production-positioned tool (LTX Studio, Visla, Kling, Sora
Storyboard) pairs longer-form support with a storyboard-first approval gate; the clip
generators that skip review (Runway, Pika, NotebookLM) cap out short.

**Length scaling makes the review gate economically necessary; the review gate makes length
scaling safe.** Ship them together, weighted by length.

extrovid already starts on the right side of this: `run_storyboard` plans **per-scene** with a
continuity baton (`orchestrator.py:273`, already breaks the 5–10-shot ceiling), pauses at
`STORYBOARDED` (`api/pipeline.py:123`), chains keyframes, and has Cast portraits +
revise/trim/reorder. The engine exists. What's missing is (1) an above-scene structure layer
+ tier-aware planning, and (2) a real review/annotate gate.

## 1. Locked decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Length ambition | Up to **~20 min** (long tier). Raise caps **behind the long tier only**: `MAX_TOTAL_SHOTS` 80→~160, `target_duration_sec` le 600→~1200, `MAX_SCENES` relaxed under chapters. Short/medium caps unchanged. |
| 2 | Architecture | **Option A** (single parametric pipeline, `Tier` enum derived from `target_duration_sec`, format = prompt modifier) **+ Option D** chapter/act layer for **long only**. No recursive rewrite. |
| 3 | HITL | Review-gate strictness **scales with length**: SHORT optional/skippable (keep one-prompt-to-video), MEDIUM default-on, LONG mandatory + cost confirmation. |
| 4 | Cost | **Per-project budget** approved at the gate (est USD from `pricing`/`config` rates); best-of-N gated by tier; `default_daily_video_cap=3` insufficient for long. |
| 5 | Review model | **R1 lightweight inline, single-user.** Anchored annotations → existing `revise_service`. Multi-reviewer collaboration (R2) deferred. |
| 6 | Long gating | **Double-gate** for long: review the cheap chapter/outline map **before** per-scene storyboards generate, then the storyboard gate. Short/medium = single storyboard gate. |
| 7 | Annotation→change | **Propose-diff + per-item accept/reject** (non-destructive). Wrap `revise_service` to return a proposal; commit on accept. |
| 8 | Still-vs-motion | System **suggests stills** for low-motion scenes; user confirms at the gate (`render_mode: video|still`). |

## 2. Length tiers

Tier is derived in Python from `target_duration_sec` (no new user input; overridable later via
Clarify). Boundaries: **SHORT ≤ 90s**, **MEDIUM 91–300s**, **LONG > 300s** (up to ~1200s).

| | SHORT ≤90s | MEDIUM 91–300s | LONG 301–1200s |
|---|---|---|---|
| Scenes | 1–3 | 3–6 | 6–12 (grouped into 3–5 acts) |
| Structure | hook → body → payoff | setup → development → resolution / problem→solution→CTA | multi-act, each ~60–120s w/ mini-hook + handoff |
| ASL (avg shot len) | ~2.5s | ~3.5s | ~4.5s |
| Continuity | `_scene_tail` baton (current) | + continuity bible (cast + locations + props) | + cross-act keyframe chain + re-anchor to portraits every K scenes |
| Script call | single | single | **per-chapter chunked** (token safety) |
| Review gate | optional / skippable | default-on | **mandatory + cost confirm**, double-gate |
| Render | best-of-N free | show est cost, nudge N=1 | keyframe-first parallel; N limited to anchor/dialogue shots |
| Caps | unchanged | unchanged | raised behind tier |

## 3. Architecture (Option A + D)

Keep the single linear `orchestrator.run_pipeline` (Brief → Script → Cast → VisualDev →
per-scene Storyboard). Branch **prompts, scene-count/ASL targets, continuity depth, and
review-gate strictness** off a `Tier` enum. For **long only**, insert a Chapter/Act layer (a
nullable `Scene.act_id` + a light `Act` table) and an outline-first gate — reuse the existing
per-scene fold within each chapter, with `_scene_tail` as the cliffhanger handoff.

This reuses the per-scene fold, `_scene_tail` baton, `replace_*` persist, `revise_service`, and
the whole (scene-keyed) frontend. Tiers are config, not forks — the existing ~234 tests stay
valid; tier branches are additive.

## 4. Data-model changes (by phase)

- **P0** — none. `Tier` lives in code (`app/agents/tiers.py`), derived from `target_duration_sec`.
- **P1** —
  - `ProjectStatus`: add `AWAITING_REVIEW`, `APPROVED` (currently DRAFT/SCRIPTED/STORYBOARDED).
  - `Scene` + `Shot`: add `approved: bool`, `locked: bool`, `approved_at: datetime|None`.
  - New **`Annotation`** table: `id, project_id, target_kind (scene|shot|visual_brief), target_id, field (nullable), intent (comment|change|approve), text, status (open|applied|resolved), created_at`. Anchors must re-bind across regenerate (`replace_shots` clears+inserts).
  - Minimal **plan snapshot** on Approve (JSON) for the diff/rollback baseline.
- **P2** — `Shot`/`Scene` `render_mode: video|still`. (Continuity bible is prompt-side, no schema.)
- **P3** — nullable `Scene.act_id` + `Act` table `{id, project_id, order, title, hook, open_loop}`. Raise `MAX_TOTAL_SHOTS`/`MAX_SCENES`/`target_duration_sec` le **behind the long tier**.

All schema changes ship with an Alembic migration (`backend/migrations/`).

## 5. Backend changes (by phase)

- **P0** (no new endpoints):
  - `app/agents/tiers.py`: `Tier` enum, `tier_for(sec)`, per-tier ASL/scene-range/structural template, `script_tier_block()`, `scene_shot_tier_block()`.
  - De-hardcode prompts: `SCRIPT_SYSTEM` ("short-form video scriptwriter" → length-agnostic), `CLARIFY_SYSTEM` ("a short video" → "a video"). Inject the tier block into `build_script_prompt` and `build_scene_storyboard_prompt`; add the named HOOK for SHORT scene 0.
- **P1**:
  - `POST /projects/{id}/plan/approve` (whole-plan or `{scene_ids}`), `/scenes/{id}/lock`+`/unlock`, `/shots/{id}/lock`, `POST /annotations`, `GET /annotations`, `POST /annotations/{id}/resolve`.
  - **Gate** `generation.py` endpoints (`/generate-all`, `/scenes/{order}/generate-all`, `/shots/{id}/generate`) → 409 unless approved (tier-dependent: short may auto-approve/skip). Extend `project_state.snapshot` with an `approval` precondition + projected cost (USD via `config` rates).
  - Wrap `revise_service.revise` to optionally return a **proposed diff** (old+new) instead of committing; commit on accept. Its `scene:`/`shot:`/`visual_brief:` dispatch already matches annotation anchors 1:1.
  - An `intent=change` annotation calls revise with the target derived from its anchor.
- **P2**: per-scene `render_mode` plumbed into `generate_service` (still → keyframe only, skip video); continuity bible injected into every `scene_storyboard_agent` call (extend `cast_block` with locations/props/established look).
- **P3**: `POST /plan/outline` (chapter map, reviewable before per-scene storyboards); per-chapter `/storyboard`; per-project budget + long-tier cap in `usage_service`; keyframe-first parallel render policy; cut-level pacing pass via existing trim/reorder.

## 6. Frontend changes (by phase)

- **P0** — none (internal planning quality only).
- **P1** — turn `Workspace.tsx:621` `onPlanned` (which today jumps to the look tab, no gate)
  into a **Plan Review** surface:
  - Approval header: scene count, total shots, est. duration, **projected cost**, one
    `Approve & Generate` button.
  - **Progressive disclosure**: collapsed scene cards → expand to shots (`ShotBoard` filmstrip)
    → expand a shot to fields (`ShotInspector`). Never render 80–150 shots flat (current
    `ShotBoard` single horizontal scroll breaks at scale).
  - **Per-element anchored annotations** (scene card / shot tile / field) with a comment badge;
    `intent=change` wires to the existing `/revise`.
  - **Propose-diff**: revise output shown old-vs-new with per-item ✓/✗ (Google-Docs-suggesting
    pattern), not in-place overwrite.
  - **Approve/lock** toggle per scene/shot; locked elements excluded from full-regen.
  - Lenses on one approvable plan: DOCUMENT (`PlanPanel`), BOARD (`ShotBoard`), TIMELINE.
- **P2** — per-scene **still-vs-motion** toggle at the gate (suggested + confirm); variant
  stacking via the existing best-of-N takes strip.
- **P3** — act/chapter accordion above scenes; outline-first review screen; cost/budget gate UI.

## 7. Test plan

- **P0** — new `tests/test_tiers.py`: `tier_for` boundaries (90/91/300/301); `script_tier_block`
  / `scene_shot_tier_block` contain the right structural cues per tier; SHORT scene 0 carries a
  HOOK; a long brief (e.g. "a 300s documentary") still plans per-scene with contiguous orders
  and ≤15s shots (extends `test_scale.py`). Verify `test_orchestrator.py`, `test_scale.py`,
  `test_clarify.py`, `test_agents.py` stay green (no prompt-wording assertions exist today).
- **P1** — gate tests: generation 409s before approval (per tier); approve→generate succeeds;
  annotation CRUD + `intent=change` triggers a revise proposal; accept commits, reject doesn't;
  lock excludes a shot from full-regen; anchors survive `replace_shots`. Multitenancy on every
  new endpoint (reuse `get_owned_project`).
- **P2** — `render_mode=still` skips video generation and only produces a keyframe; continuity
  bible reaches the scene-storyboard prompt.
- **P3** — outline endpoint returns a chapter map; per-chapter storyboard; long-tier caps allow
  >80 shots only on the long tier; per-project budget blocks over-budget generation.

## 8. Phased roadmap (PR-sized)

| Phase | Scope | Effort |
|---|---|---|
| **P0** | De-hardcode short-form + `Tier` scaffolding (prompts + helper). No DB. | S (1–3d) |
| **P1** | Lightweight review gate: status/approve/lock/annotation/diff + Plan Review UI + generation gating. | M (1–2wk) |
| **P2** | ✅ Continuity bible + non-destructive diff "apply exact" + demote-on-revise. (still-vs-motion → P3.) | M |
| **P3** | LONG tier: chapter layer + outline-first gate + cost/cap/budget policy + keyframe-first render + **still-vs-motion** (render_mode + cut freeze-frames). | L (3–5wk) |
| P4 (deferred) | Collaborative review (share links, threads), multi-scale audio, ViMax-style RAG. | XL (demand-gated) |

## 9. Risks & mitigations

- **Prompt-only tier scaling may miss scene/shot counts** (duration→scene is LLM-driven:
  `scale = target/total_est`, `orchestrator.py:288`). Mitigate with tier tests and, if needed,
  a Python floor `expected_shots = budget/ASL`.
- **Continuity drift** is the dominant long-form failure; baton + per-take review aren't enough
  at 30–80+ shots. Mitigate with the continuity bible (P2) + portrait re-anchoring (P3).
- **Cost explosion**: gate best-of-N by tier + per-project budget + cost estimate at the gate.
- **Serialization**: continuation chains serialize ~90s/shot at `video_rpm=2`; prefer
  keyframe-first parallel render for long (P3).
- **Script token budget**: single-call script breaks for long → per-chapter chunking (P3).
- **UX at scale**: progressive disclosure is a hard prerequisite — the gate is unusable for
  long until `ShotBoard` stops rendering all shots in one scroll.
- **Lock vs staleness cascade**: editing scene N's last keyframe affects N+1's first-frame
  chain; new lock/approve state must interact correctly with `revise_service` staleness.
- **Annotation anchor stability**: notes anchored to `shot_id` must re-bind after
  `replace_shots` clears+inserts, or they orphan.

## 10. Code anchors

`orchestrator.py:273` `run_storyboard` (per-scene fold + `_scene_tail` baton) ·
`orchestrator.py:207` legacy "Produce 5-10 shots" literal ·
`prompts.py:82` "short-form video scriptwriter" + `CLARIFY_SYSTEM` "short video" ·
`schemas/pipeline.py:47` `target_duration_sec ge=5 le=600` ·
`enums.py` `MAX_TOTAL_SHOTS=80 / MAX_SCENES=15 / MAX_SHOTS_PER_SCENE=10` / per-shot ≤15s ·
`api/pipeline.py:123` sets `STORYBOARDED` · `Workspace.tsx:621` `onPlanned` (no gate today) ·
`revise_service` dispatch on `scene:`/`shot:`/`visual_brief:` ·
`config.py:131` `default_daily_video_cap=3` · `config.py:143` video per-sec cost rates ·
`providers/mock_data.py` `_parse_target_from_brief` clamps 5–600 (raise with the long-tier cap).
