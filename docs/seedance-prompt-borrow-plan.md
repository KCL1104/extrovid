# Seedance2-skill → extrovid: video-prompt borrow plan

Source: `dexhunter/seedance2-skill` (ByteDance Jimeng Seedance 2.0 prompt guide).
Verdict from prior analysis: extrovid already matches/beats the guide on architecture
(3-view portraits, keyframe gate, continuity review, native `negative_prompt`, structured
camera slots, keyframe chaining, length tiers). The worthwhile borrows are all **cheap
prompt-text / vocabulary changes**, not architecture.

All edit-specs below were verified verbatim against the live code (deep-read, all `feasible=true`).
Line numbers are approximate anchors — confirm at edit time.

---

## Phase 1 — Core prompt-text trio  (effort: S, risk: low)

Pure string/constant changes. Two files: `app/agents/prompts.py`, `app/services/prompt_service.py`
(+ `app/schemas/pipeline.py` Field descriptions). No schema/signature change.

### #1 Controlled cinematic camera vocabulary
- **#1a** `app/schemas/pipeline.py` — expand Field descriptions on `CameraSpec.shot_size` (~231),
  `.angle` (~232), `.movement` (~233) to a controlled menu. Keep `str` + `min_length=1` (no enum).
  - shot_size: `ECU, CU, MCU, MS, full, wide/establishing`
  - angle: `eye-level, low, high, dutch, overhead/bird's-eye, POV`
  - movement: `static, slow push-in, pull-back, pan L/R, tilt up/down, track/follow, orbit, crane, handheld; advanced when motivated: dolly-zoom (Hitchcock), whip pan, first-person POV`
- **#1b** `app/schemas/pipeline.py` `ShotDTO.motion_desc` (~325-332) — replace the loose
  "professional camera terms (dolly, pan, push-in)" parenthetical with a pointer to the same
  movement menu; keep the bare-name anchoring sentence verbatim.
- **#1c** `app/agents/prompts.py` `_STORYBOARD_BODY` (shared by `SCENE_STORYBOARD_SYSTEM` +
  legacy `STORYBOARD_SYSTEM` — one edit covers both) — insert a "Camera vocabulary:" paragraph
  between the camera-positions paragraph (~153) and the "Keyframe contract:" line (~154).

### #2 Conflict / physical-plausibility guardrail
- `app/agents/prompts.py` same `_STORYBOARD_BODY` — append two sentences just before the closing
  "Return only the structured object." (~158):
  1. *Camera consistency:* `camera_spec.movement` must agree with `motion_desc` (never a static
     movement with a moving-camera motion_desc).
  2. *One action per shot:* keep each shot to one primary action achievable within its
     `duration_sec`; split multi-action beats into separate shots.
- **CRITICAL wording rule:** do **not** use the word "Avoid" anywhere — a test asserts `"Avoid"
  not in` the positive prompt. Use "do not" / "never" / "no".

### #5 Global negative-prompt baseline
- `app/services/prompt_service.py` — add module-level `_BASELINE_NEGATIVES` tuple after
  `_SIDE_VIEW_CUES` (~32): `deformed hands, extra fingers, extra limbs, warped face, flicker,
  text artifacts, watermark`.
- `compose_negative_prompt` (~255-259) — append `_BASELINE_NEGATIVES` **after** authored sources
  (visual_brief / style_pack / character.forbidden_changes), dedupe, raise cap 6→8 so authored
  rules win the cap. Function now (almost) never returns `None`.

**Tests (Phase 1)**
- UPDATE `tests/test_promptcraft.py:test_visual_brief_reaches_the_prompt` — `compose_negative_prompt(...)
  == "no harsh shadows"` → `"no harsh shadows" in neg`.
- ADD `test_negative_prompt_baseline_when_no_authored` — no-arg call returns non-None containing `watermark`.
- ADD `test_authored_negatives_win_cap` — 8+ authored: all survive, baseline dropped past cap.
- ADD `tests/agents/test_prompts.py` — both storyboard systems contain `Camera vocabulary`,
  `orbit`/`Hitchcock`/`establishing`, `Camera consistency:`, `One action per shot:`, and no `Avoid`.
- OPTIONAL `tests/test_pipeline_schemas.py` — `CameraSpec.model_fields['movement'].description` mentions the menu.

---

## Phase 2 — emotion→TTS + prompt hygiene  (effort: M, risk: low-med)

### #4 Wire `performance_spec.emotion` into the TTS instruction (revive dead path)
- `app/services/audio_service.py` `synthesize_shot_voiceover` (~71-76) — before the
  `synthesize_speech` call compute:
  ```python
  emotion = str((shot.performance_spec or {}).get("emotion") or "").strip()
  instruction = f"Speak with a {emotion} tone." if emotion else voice.get("instruction")
  ```
  and pass `instruction=instruction`. Activates the existing `qwen_tts_instruct_model` branch only
  when emotion is set. No `resolve_voice` signature change; voice_lock untouched; no billing impact.
- ⚠ `qwen_tts_instruct_model` name + `inp['instruction']` field are unverified against a live intl
  TTS key (per `audio_factory.py` header note). Under `use_mock_tts=True` (default) fully deterministic.

### #6 Prompt hygiene (each sub-item independently togglable)
- **#6a** `compose_shot_prompt` (~88-100) — set `appearance_inlined = True` in the subject-rewrite
  branch; in the character-constraints block (~162-167) emit bare `featuring {name}` when inlined
  (drop redundant `: {desc}`), else keep full desc. Wardrobe line unchanged.
- **#6b** remove the trailing `parts.append(f"beat: {shot.beat}")` (~177) — internal planning
  metadata, not visual direction. Field stays on the model.
- **#6c** dialogue line (~140-142) — **DEFAULT: no change** (keep verbatim, see Decisions).

### #7 Default style/lighting fallback (OPTIONAL — recommend defer)
- `compose_shot_prompt` — add `_DEFAULT_STYLE` / `_DEFAULT_LIGHTING` constants and an `else` branch
  on the style (~150) and lighting (~153) blocks, guarded strictly on emptiness.
- Highest blast radius of the phase (every bare shot gains `style:`/`lighting:`); can distort eval
  style-coverage metrics. Defer until evals re-baselined.

**Tests (Phase 2)**
- ADD `tests/test_audio.py:test_emotion_drives_tts_instruction` — `performance_spec={'emotion':'anxious'}`
  → instruct model; empty emotion → base model.
- UPDATE `test_promptcraft.py:test_bare_shot_still_produces_a_prompt` — drop `"beat: hero moment" in p`;
  assert `"beat:" not in p`, prompt ends with `.`, `"Avoid" not in p`.
- UPDATE `test_appearance_anchored_subject`, `test_style_pack_and_character_injection`,
  `test_shot_update.py:test_generate_*_character*` — retarget `"featuring X:"` discriminators to
  name/appearance tokens (appearance now reaches prompt via inline anchor, not the `featuring` tail).
- `#7` (if shipped) ADD default-present + explicit-suppresses-default pair.

---

## Phase 3 — Role-tag caller reference images  (#3, effort: M, risk: medium — heaviest)

Attach optional Seedance-style roles to caller refs and surface a role clause in the prompt.
Only item touching API contract + persisted `gen_params`.

- **Schema** `app/schemas/api.py` — `ReferenceRole = Literal["identity","outfit","prop","scene","style"]`
  (Literal + model_validator already imported). Add `reference_roles: list[ReferenceRole] | None = None`
  to `GenerateShotRequest` + a `model_validator(mode="after")` requiring len-match with
  `reference_asset_ids` (else 422).
- **API** `app/api/generation.py` `generate_shot` (~124-134) — forward `reference_roles`.
- **Service** `app/services/generate_service.py` — thread `reference_roles` through `submit_shot_batch`
  (~552), `submit_shot` (~338), persist into `gen_params` only when present (~368-378), read back in
  `_activate_submission` (~417-422) and pass to `compose_shot_prompt` (~483-490).
- **COMPANION EDIT (required)** `retry_job` (~809-818) currently drops `reference_roles` — add
  `reference_roles=params.get("reference_roles")` or retried takes silently lose roles.
- **Prompt** `app/services/prompt_service.py` — `_REFERENCE_ROLE_CLAUSE` dict
  (outfit→"the subject's wardrobe matches the reference image", prop→"the object/prop matches…",
  scene→"the scene/background matches…", style→"visual style references…"; identity folded into the
  existing portrait line); add `reference_roles` param, append deduped clauses after the identity
  clause (~78-84). Default `None` → byte-identical output.
- **Note:** positional `roles[i]→asset_ids[i]` does NOT survive `_resolve_reference_urls`
  reorder/dedupe/4-cap. Acceptable: roles drive only the prompt *clause*, not per-URL provider
  binding (`submit_video` takes a flat `reference_urls` list, no role channel).

**Tests (Phase 3)**
- VERIFY default (no `reference_roles`) → byte-identical prompt.
- ADD role-clause cases (outfit/prop), identity-only adds nothing, unknown role ignored.
- ADD `tests/test_r2v.py` — paired POST carries clause; mismatched-length → 422; refs-only still 200.

---

## Decisions needed
1. **#6c dialogue cue** — DEFAULT **A: keep verbatim** (gives i2v model phoneme/length signal for
   lip-sync; diffusion video does not render the literal text on-screen). B (generic "lips moving in
   sync, ~N words") only if a provider proves to render literal text.
2. **#3 ship now or defer** — only item touching the API contract; delivers a prompt *clause* (not
   true per-reference provider tagging, unsupported today). Ship minimal now, or defer until the
   Board Room FE actually sends paired roles.
3. **#6a description tail** — when inlined, `featuring {name}: {desc}` → bare `featuring {name}` drops
   multi-sentence tails (e.g. "Mid-30s."). Accept the drop (simplest) or append only the remainder.
4. **#7 style/lighting defaults** — ship now vs defer (recommend defer until evals re-baselined);
   confirm house defaults if shipped.

## Sequencing
- Order Phase 1 → 2 → 3 (effort/risk/blast-radius). Phases are code-independent → separate commits.
- #1 + #2 both edit the single `_STORYBOARD_BODY` — do in one pass; keep #2 free of the word "Avoid".
- #5 + #6/#7 all edit `compose_shot_prompt`/`compose_negative_prompt` — sequence so
  `test_promptcraft.py` is updated once per phase.
- #3 MUST include the `retry_job` companion edit.
- **Run the full pytest suite at the end of each phase** (the ~234-test suite is the gate).
- After any phase ships, `app/evals` baselines shift (richer camera strings, always-on negatives) —
  re-record goldens next eval run; expected, not a regression.

## Out of scope
- No enum/Literal for camera fields (stay free-text str → PydanticAI/JSON-Schema unchanged).
- No code-level guardrail enforcement (#2 is prompt-instruction only).
- No true per-reference provider @-tag binding (`submit_video` has no role channel).
- No second `cam_desc` render (~223 keyframe/still path), no keyframe-prompt style defaults, no FE work.
