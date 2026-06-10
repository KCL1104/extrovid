# ViMax (HKUDS) Research — What to Adopt for extrovid

**Date:** 2026-06-10
**Source studied:** https://github.com/hkuds/vimax (cloned at full depth, every subsystem read: 3 pipelines, 14 agents, agent runtime, provider tools, interfaces, prompts; claims spot-verified against source by an adversarial critic pass).
**extrovid baseline:** post-PR9 (`2aeb7ed`).

---

## 1. What ViMax is

ViMax is HKUDS's agentic video-generation framework (arXiv 2606.07649): idea/script/novel → multi-agent planning → image keyframes → video clips → concat. Three pipelines:

- **idea2video** — Screenwriter develops a story, extracts characters, generates portraits, writes per-scene scripts, then runs script2video per scene with a **shared character-portrait registry** (that sharing *is* the cross-scene consistency mechanism), then moviepy-concats.
- **script2video** — the core renderer: storyboard (shots + camera assignment) → per-shot first/last-frame/motion decomposition → keyframe **images** generated with reference selection → videos generated from keyframes + motion text → concat.
- **novel2movie** — the long-form front-end: novel compression (64K-char chunks, 8K overlap, parallel map + LLM reduce), autoregressive event extraction (one event per call until `is_last`), FAISS RAG over the *raw* novel to recover compression loss, scene extraction grounded in original prose, global character registry folded event-by-event. **Header literally says `# TODO: NOT IMPLEMENTED YET`** — the planning path is wired via the agent runtime, but treat it as a design reference, not battle-tested code.

It also ships an interactive **agent loop + TUI**: one tool-calling LLM loop over 3 coarse pipeline tools + file/memory utilities, with per-turn state grounding, staleness cascades on revision, and context compaction.

### Core philosophy worth internalizing

1. **Identity and geometry route through pixels, not prose.** Characters become canonical portrait images; every keyframe is generated *as an image* with portrait references; the video model only animates. Text describes motion; images carry identity.
2. **No planner ever sees more than one scene.** Long video = hierarchy (novel → events → scenes → shots → keyframes), each level fits one context window, structural indices computed in Python, per-item checkpointing.
3. **Generation-aware writing doctrine.** Prompts are written for what a diffusion model can render: no metaphors, no pronouns, appearance-not-name, static "snapshot" keyframe descriptions, repetition over elegance.
4. **Validation-driven retry, not prompted self-critique.** Invariants checked in Python (index echo asserts, bidirectional coverage checks) raise into retries.

### Marketing vs. reality (verified — do not cite these as ViMax precedent)

| README/paper claim | Reality |
|---|---|
| "Automated Image Generation Consistency Check" (best-of-N + VLM judge) | `best_image_selector.py` is **dead code** — zero call sites. Every image call generates exactly one candidate. |
| AutoCameo (your photo → video) | Zero code anywhere. |
| "Audio and Video Binding" | No TTS, no audio assembly. `audio_desc` is plain text appended to the video prompt — only meaningful for Veo 3.x native audio. |
| "Asset indexing — embeddings, retrieval for reuse" | Only FAISS over raw novel *text*. No visual-asset index. |
| "Tracks environmental states across temporal boundaries" | Environment is a static per-scene text field. |

Known ViMax bugs (extra reason to adopt patterns, not code): `priority_shot_idxs` mixes camera/shot indices (`script2video_pipeline.py:230` vs `:418`); class-level `asyncio.Event` dicts shared across pipeline instances (two of three vestigial); unbounded `while True` retry in Seedance provider; bare infinite `@retry` in utils; compactor fallback `NameError`; broken legacy `Novel2MoviePipeline.__call__`.

---

## 2. Where extrovid is already ahead (keep, don't regress)

- **Job lifecycle**: Postgres `ShotVersion`/`GenerationJob` lineage, `gen_params` exact-replay retry, reconciler, timeouts — ViMax has filesystem `os.path.exists` checkpoints.
- **Quality gate**: auto ReviewAgent with vision on every ingest, scores + suggestions. ViMax has **no wired review at all**.
- **Assembly**: ffmpeg xfade/captions/audio bed/normalize rough cut vs. ViMax's bare moviepy concat.
- **Schema-enforced budgets**: typed duration/shot-count validators + `ModelRetry` vs. ViMax's prose-only "not more than 5!!!".
- **HTTP resilience**: bounded backoff honoring `Retry-After` vs. infinite retry loops.
- **r2v compositional richness**: ≤5 reference images *plus* first-frame seed in one call — ViMax's omni mode tops out at 3 refs without a seed.

---

## 3. Adoption roadmap (consolidated from 5 theme analyses, ranked by impact-per-effort)

### Tier 1 — prompt/text-level quick wins (S each, no migrations, ship first)

**A1. T2V-aware writing-rules pack.** Add a shared `T2V_WRITING_RULES` block to `SCRIPT_SYSTEM`, `VISUAL_DEV_SYSTEM`, `STORYBOARD_SYSTEM` in `backend/app/agents/prompts.py`:
- *No metaphors/similes* — the model renders them literally (ViMax repeats "No metaphors allowed!!!" with negative few-shots in every script template, `script_planner.py:30,58,94,177`). `grep -ri metaphor backend/app` → zero hits today.
- *Show, don't tell*: "he turns away, avoiding eye contact" not "he feels ashamed" (`screenwriter.py:103`).
- *Name the subject explicitly in every description; no pronoun carry-over* — each shot generates in isolation.
- *Describe only what is visible in frame* (incl. ViMax's `EnvironmentInScene` rule: setting descriptions exclude characters/actions).
Also adopt the **schema-as-prompt** habit: rich `Field(description=, examples=)` on `PerformanceSpec.action`, `ShotDTO.purpose` (PydanticAI ships field metadata to the model).

**A2. Appearance-anchored subjects (appearance-not-name rule).** ViMax's most load-bearing single rule: the video model never sees the character bible, so *"'Alice is walking' is unacceptable; it should be 'Alice (short hair, wearing a green dress) is walking'"* (`storyboard_artist.py:104`). In `prompt_service.compose_shot_prompt`, when a cast lock exists, render the subject inline as `{name} ({appearance excerpt}, {wardrobe_rule})` next to the action — and adopt repetition-for-precision ("accuracy over rhythm; redundancy is acceptable", `script_enhancer.py`).

**A3. Native `negative_prompt` parameter.** Not from ViMax (it has none) — the gap analysis exposed that our "Avoid: …" suffix inside the *positive* prompt is the weakest link. Split `compose_shot_prompt` → `(prompt, negative_prompt)`, pass as a real `parameters.negative_prompt` to Wan/Qwen (verify exact param name in real mode; fall back to suffix if rejected). Store in `gen_params` for retry fidelity.

**A4. Continuity-aware review.** Attach the *previous shot's* selected-take frame as a second `ImageUrl` in `review_service.review_version` ("Image 1 = final frame of previous shot; Image 2 = take under review") + one REVIEW_SYSTEM paragraph borrowing ViMax's judge rubric: character features (gender/age/facial/body/hairstyle), wardrobe, palette, and **spatial layout must not flip** (left/right preservation, `best_image_selector.py:18-39`). Optional `continuity_notes` on `ReviewResult`. Closes the spec's cross-shot continuity gap nearly for free.

**A5. Spatial grounding / blocking field.** Add `framing: str | None` to `ShotDTO` ("Maya on left third, facing right, focus on her hands") + STORYBOARD_SYSTEM rules from `storyboard_artist.py:47,51,52`: state each subject's frame position and facing direction; name the body part in focus. Feeds `compose_shot_prompt` and makes `match_cut` and review acceptance actually checkable.

**A6. Persist clarify Q&A as durable creative direction.** Today `/clarify` answers bend only the Brief and are then discarded — "anime style, melancholy ending" can evaporate by storyboard stage. Add `clarifications` JSON column on `Brief`; render a `creative_direction_block` into script/visual/storyboard prompts and `compose_shot_prompt`. (ViMax's per-turn re-grounding insight applied to our pipeline.)

**A7. Make r2v plannable.** `PLANNABLE_MODELS_M1` excludes r2v, so the planner systematically under-plans our highest-consistency mode. Either add it for M2 or document `preferred_model` as a hint and let reference-driven routing be authoritative (ViMax's lesson: mode follows available references, deterministically).

**A8. Proactive rate limiter.** Sliding-window rpm limiter keyed by service ("video"/"image"), acquired *before* submit. Take ViMax's semantics (`rate_limiter.py` rpm + min-spacing), **not** its implementation (it sleeps holding its lock). Needed before any fan-out work.

### Tier 2 — the consistency stack (M each, order matters)

**B1. Character portrait sheet (canonical multi-view turnaround).** ViMax's highest-leverage idea that drops straight into our r2v path. Per `CharacterProfile`: front portrait via `generate_image` using ViMax's template near-verbatim (*"full-body, front-view portrait … pure white background … centered … gazing straight ahead, arms relaxed at sides, natural expression. Features: … Style: …"*, `character_portraits_generator.py:17-22`), then **side/back as `edit_image` of the front view** ("Facing left" / "No facial features should be visible") so all views are the same person. Store `{front, side, back}` asset ids on the profile (can repurpose dead `face_lock`); prepend to `_resolve_reference_urls`. Wan r2v locks identity far better from clean white-background turnarounds than from busy in-scene look frames, and side/back coverage is exactly what fails on profile/from-behind shots.

**B2. Cast extraction agent (auto-populate what B1 consumes).** New `CastAgent` after `run_script`, prompt adapted from `character_extractor.py:15-47` with its three load-bearing rules: features must be *visualizable only* ("specific clothing colors, large eyes, a high nose bridge" — ban personality/role/relationships), *invent plausibly* when the script is silent, *make cast members visually distinct* (anti identity-collision). Static features → `description`, dynamic → `wardrobe_rules`. Auto cast-lock: have StoryboardAgent emit `character_name` per shot, match to profiles. Today CharacterProfiles only come from manual promote — most projects render with zero identity anchoring.
*Skip ViMax's celebrity-likeness rule ("retain the real person's name, e.g. Elon Musk") — IP risk + DashScope content filters.*

**B3. Best-of-N take fan-out with review-driven auto-select.** The recommendation ViMax designed but never wired — extrovid has every missing piece already (judge, `selected` semantics, lineage, caps). `num_takes: int = 1..4` on generate; tag siblings with `batch_id` in `gen_params`; when all terminal, auto-select highest-scoring pass. Phase 2: comparative `BestTakeAgent` over sibling poster frames using ViMax's rubric (character-feature checklist a–g, spatial left/right preservation, "no white borders/black edges"; `best_image_selector.py:12-40`) — side-by-side beats independent absolute scores. Apply to *images first* (portraits, keyframes): stills are ~30× cheaper than takes.

**B4. Dialogue→shot binding with persistent voice descriptors.** `SceneBeat.dialogue` never reaches generation today (subtitles only). ViMax: *one dialogue line per shot*, speaker prefixed with a short **byte-identical** voice descriptor every time (`script_enhancer.py` examples; future-proofs TTS, finally uses dead `voice_lock`). Add `dialogue`/`sound_notes` to `ShotDTO`+`Shot`; fold into `compose_shot_prompt` ("spoken line: …") and prefer per-shot dialogue for caption windows in `rough_cut_service`.

### Tier 3 — keyframe-first architecture (the big structural adoption)

**C1. ff/lf/motion keyframe contract (schema + prompts, M).** Add `first_frame_desc`, `last_frame_desc`, `motion_desc`, `variation_type ∈ {small, medium, large}` to `ShotDTO`/`Shot`, with ViMax's decompose rules near-verbatim (`storyboard_artist.py:73-110`): keyframe descriptions are *pure static snapshots* ("'about to stand up' is unacceptable; 'sitting, leaning slightly forward'"); motion uses professional camera terms and visible-attribute character references; last frame reflects all motion. Even prompt-only (before any image generation) this improves i2v prompts, makes continuation deliberate (planned end-state vs. whatever Wan produced), and gives review a checkable target (`extract_last_frame` already exists — verify the take ends as planned).

**C2. Per-shot keyframe generation (L, decomposable).** Generate every shot's first frame **as an image** before video: refs = portrait views (B1) + style pack; identity-anchored via `edit_image` from the character's reference frame (the same base-portrait→scene-variant move as `novel2movie_pipeline.py:413-417`); judged via B3; stored as a shot-scoped LookFrame (existing `/refine` flow works on it for free); preferred as `first_frame_asset_id` in `submit_shot` routing. Payoffs: iteration is image-priced before video-priced; identity resolves in the image domain where reference conditioning is strong; **continuity stops depending on rendered video** (today a 40-shot chain renders strictly serially through `continue_from_previous`).

**C3. Per-scene storyboard planning (S/M — the long-video gate).** ViMax's core scaling move: no planner sees more than one scene's shots. Fan `run_storyboard` out per scene (mirror the existing per-scene `run_visual_plan` gather), per-scene shot caps, global `Shot.order` renumbered in Python (never ask the LLM for global order). Raise `target_duration_sec` ceiling and `ScriptDraft.scenes` max. Breaks the 5–10-shot / 120s ceiling — prerequisite for everything long-form.

**C4. Dependency-aware batch scene rendering (M).** `POST /scenes/{n}/generate-all`: shots with keyframes submit in parallel; continuation-only shots register a `pending_dependency_shot_id` on the queued job and the **existing reconciler** submits dependents when the upstream take ingests. DB-backed, restart-safe — deliberately *not* ViMax's in-memory class-level `asyncio.Event`s.

**C5. First+last-frame conditioning (M, provider-gated).** `variation_type` medium/large → generate both keyframes and route to a kf2v model (DashScope keyframe-to-video family — **verify availability on our account first**; ViMax does this via Veo `config.last_frame`, `video_generator_veo_google_api.py:49-57`). Shot N's planned last frame doubles as shot N+1's seed → image-level chaining replaces video-extraction chaining. If kf2v is unavailable, scope shrinks to "continuation seed = generated last frame", still worthwhile.

**C6. Timeline-aware reference selection (M, last).** Once B1/C2 exist the ref pool outgrows the naive `[:5]` truncation. Adopt ViMax's selection *priors* (`reference_image_selector.py:99-108`), deterministic tier first: at most **one portrait view per character**, view matched to shot direction (back view for over-the-shoulder), recency preference for prior-frame refs, drop a portrait if a recent frame already shows the face; `Image N` element-binding lines in the prompt. Optional flagged LLM tier (text-only captions, one cheap call). Skip ViMax's two-stage multimodal architecture — our pools stay ≤8 captioned URLs.

### Tier 4 — director runtime (independent track)

**D1. Project state snapshot + dependency gating (S).** `GET /projects/{id}/state`: pure-DB checklist (modeled on ViMax's `artifact_checklist`, `session_index.py:181-222`) + `dependency_missing`-style 422s on generate/rough-cut (*"reports missing dependencies instead of pretending render started"* — `vimax_adapters.py`).

**D2. Targeted revision + staleness cascade (M).** `POST /projects/{id}/revise {target, instruction}` → small ReviseAgent with same-schema structured output ("revise exactly as requested; preserve everything not covered"); staleness mapping translated from `_stale_keys_for_revision` (`vimax_adapters.py:674-685`): brief→all; scene→its concepts+shots; shot→its takes. `stale` flag on rows, surfaced as "stale — replan?" badges. Biggest iteration-cost gap vs. ViMax: our replace-semantics endpoints regenerate whole slices and silently orphan downstream work.

**D3. Tool-calling DirectorAgent (L).** PydanticAI agent (native tool loop — do **not** port ViMax's hand-rolled loop) wrapping existing services as tools: `plan_*`, `revise_artifact` (D2), `generate_shot`/`assemble_rough_cut` (gated by D1), `get_project_state`, `get_review`/`apply_review_suggestion` (closes the review→revise loop ViMax lacks). Adopt ViMax's two prompt policies verbatim-in-spirit (`prompts/agent.md`, `workflow.md`): the **grounding contract** ("do not claim planning/rendering happened unless a tool result proves it") and the **stage gate** ("when planning is complete and the user didn't ask to render, call no tool — report and ask"). History = flat recent turns + per-turn state snapshot, *not* transcript replay (`loop.py:115`). Cap tool passes (~8). Later: rolling summary column (ViMax's compaction schema: Active Task / Completed Actions / Decisions / Errors & Risks / Remaining Work, labeled "reference context only, not active instructions") and SSE streaming of `tool_start/tool_result` events.

### Tier 5 — long-source import (after C3 + B2)

**E1. Novel/script/transcript → project (L).** Port the novel2movie *patterns* to PydanticAI: chunk-compress with overlap-dedup reduce (`novel_compressor.py:47-70`); autoregressive event extraction with the **index-echo assert → retry** trick (`event_extractor.py:141`) as a `ModelRetry` validator; `process_chain` causal steps per event; scene extraction grounded in source prose ("every line of dialogue has a basis in the original text"); the **alignment-table character fold** (`global_information_planner.py:216-272` — LLM returns only `{index_in_novel | -1}` mappings, Python applies the merge so the model never corrupts the registry) with its bidirectional coverage validation. `SourceEvent` table replaces ViMax's JSON files (resume = `max(index) where not is_last`). **Defer FAISS+reranker RAG** — pass raw-text windows located by string search until genuinely book-length sources demand embeddings (our only would-be new infra dependency).

---

## 4. Explicitly not adopting (and why)

- **Camera tree + transition-video angle bootstrap + PySceneDetect** (`camera_image_generator.py:153-202`): ViMax's most original mechanism — new camera angles are mined by asking the *video* model to film a "cut to" and scene-detecting the cut frame. Burns a full video generation per camera angle (our scarcest resource), depends on the model rendering a clean hard cut, carries a live index bug, and C2 keyframes + shared scene anchors get ~80% of the value at image prices. The cheap rider we do take: a `camera_id: int` field + reuse guideline on shots ("reuse an existing camera position when possible; a camera that performs significant movement may not be reused") — same-camera adjacency is a strong continuation heuristic and future-proofs this.
- **Hand-rolled agent loop / LangChain `PydanticOutputParser` / `{format_instructions}`**: PydanticAI structured outputs are strictly more reliable. Adopt the *policies*, never the plumbing.
- **Filesystem checkpoints, class-level `asyncio.Event`s, in-memory sessions**: our Postgres + reconciler is the multi-user-safe version of the same ideas.
- **`run_shell` with substring denylist, importlib `class_path` config loading**: injection-shaped foot-guns on a multi-tenant deployment.
- **moviepy concat; infinite retries; params-smuggled-in-prompt (`--rs/--dur` flags)**: we're ahead.
- **Audio/dialogue smuggled into video prompts for lip-sync**: targets Veo 3.x native audio; Wan2.7 has no audio conditioning. B4 binds dialogue for performance/captions/TTS-readiness instead.
- **Full-length exemplar scripts as few-shots** (Wandering Earth / F-18 / violin montage in `script_planner.py:344-429`): hundreds of tokens, genre-biased, leak literal refrains into output. If we later add mode-routed script prompts (narrative/motion/montage — worth considering for product-demo vs. action-teaser briefs), use elided 3–4-beat exemplars.
- **AutoCameo**: no code exists, but the *product idea* is nearly free for us (upload photo → promote as `character_ref` → r2v) — worth a product-backlog note, not an engineering adoption.

---

## 5. Suggested PR sequence

1. **PR-A (prompts)**: A1 + A2 + A5 (+ camera_id rider) — `agents/prompts.py`, `schemas/pipeline.py`, `prompt_service.py`.
2. **PR-B (quality plumbing)**: A3 negative_prompt + A8 rate limiter + A7 r2v plannable.
3. **PR-C (review + memory)**: A4 continuity review + A6 persisted clarifications.
4. **PR-D (cast)**: B2 CastAgent → B1 portrait sheets.
5. **PR-E (fan-out)**: B3 best-of-N (stills first, then takes).
6. **PR-F (keyframe contract)**: C1 schema/prompts → C2 keyframe service.
7. **PR-G (scale)**: C3 per-scene storyboards → C4 batch rendering → C5 kf2v (provider-gated) → C6 ref selection.
8. **PR-H (director)**: D1 → D2 → D3.
9. **PR-I (long-source)**: E1, after C3+B2.
10. B4 dialogue binding slots anywhere after PR-A.
