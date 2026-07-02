# Video-quality upgrades — July 2026

Research pass over how production AI-video studios (LTX Studio, Higgsfield, Seedance/Seedream
official guides, AI-filmmaking consistency workflows) get film-grade output, mapped against
extrovid's pipeline, then implemented. Three user complaints drove it: (1) image quality is
poor, (2) too many manual steps after planning, (3) prompts lack production-grade detail and
cross-scene character consistency.

## Research findings → what shipped

### 1. Image quality
Finding: lighting descriptors and camera/lens language have the highest quality leverage in
T2I models; production prompts end with an explicit render-quality floor; portraits are the
identity master whose quality compounds through every downstream keyframe/r2v shot.

- Keyframe prompts now always carry style + lighting (house defaults when the brief is
  silent, mirroring the video prompt) and a style-agnostic photographic quality tail
  (`sharp focus, rich fine detail, professional color grading, masterful composition`)
  — `prompt_service.compose_keyframe_prompt`.
- Portrait sheet template gained an explicit lighting + quality floor, and all three
  portrait generations (front gen + side/back edits) now condition on the composed
  negative prompt — `portrait_service`.
- `edit_image` (keyframe identity edits, refine loop) accepts `negative_prompt`; the
  keyframe edit path and `/refine` now pass it (previously negatives were silently
  dropped on every edit-routed image) — `image_factory` / `imagegen_service`.
- Concept-set generation uses `compose_negative_prompt` (baseline artifact floor applies
  everywhere, not just shots/keyframes).
- `VIDEO_RESOLUTION` default 720P → **1080P** (HappyHorse-native; env-revertable).

### 2. Fewer steps: one-click Produce
Finding: LTX Studio's model — define → storyboard → generate → edit, with one-click
generate-all plus per-shot retake; automation runs the pipeline, humans review at gates.

- New `produce_service` + `POST/GET /projects/{id}/produce`, `POST .../produce/stop`:
  walks portraits → keyframes → shot videos → voiceovers → rough cut, reusing the exact
  idempotent per-stage services, so each stage only does missing work and re-running
  resumes a paused/failed/restarted run.
- Human checkpoints preserved: the plan-approval review gate must be open to start;
  default `gated` mode pauses after newly CREATED keyframes (review the board before
  video budget is spent — Produce again to continue); video failures pause before
  audio/cut. `auto` mode runs straight through.
- Progress rides the existing per-project SSE event bus (`type: "produce"`); the
  workspace ShotBoard toolbar has a Produce/Continue/Stop button + live stage pill.
- The Director agent gained a `produce_project` tool ("make the whole film" in chat).

### 3. Prompt detail + cross-scene consistency
Finding: the Seedance 2.0 official formula (subject/action/environment/one camera move/
style/constraints), essential negatives (`identity drift`, jitter, flicker), reference
images as the primary identity anchor (1–4+ per generation, character sheets as master
references, every recurring face rides a ref), i2v prompts that declare the seed
authoritative ("preserve composition and colors").

- Reference capacity is provider-aware: HappyHorse 1.1 accepts 9 media items (vs Wan's 5)
  — ref cap 4 → 8 under happyhorse, seed slot still reserved (`_max_reference_images`,
  `_build_r2v_media(max_media=)`).
- **Supporting-cast refs**: characters NAMED in a shot (subject/action/motion_desc/
  first_frame_desc/speaker, word-boundary match) contribute their front portrait as an
  extra identity reference, and the prompt binds them: "the supporting cast (X, Y) each
  match their reference portraits". Previously only `shot.character_id` was anchored —
  multi-character scenes drifted.
- Negative baseline gained `identity drift` + `camera jitter`; cap 8 → 10 (authored
  rules still win ordering).
- i2v stability hint: first-frame-seeded shots (no r2v refs) append "Preserve the first
  frame's composition, palette, and subject identity."
- Writing doctrine (`T2V_WRITING_RULES`): vague-quality-adjective ban (amazing/epic/
  beautiful carry no visual information) + motion pacing rule (qualify speed to ONE
  element; unqualified "fast" degrades renders).
- Visual-dev brief: lighting must name SOURCE + DIRECTION + QUALITY; palette 3–5 concrete
  colors; environment notes tactile/filmable.

## Notes
- Eval goldens (`app/evals`) will shift (quality tails, always-on negatives, new clauses)
  — expected; re-record on the next eval run.
- Prod `.env` may still pin `VIDEO_RESOLUTION=720P`; update on deploy if 1080P is wanted.
- `negative_prompt` on the image-EDIT call is documented for qwen-image-edit; verify once
  against a live key (wan2.7-image-pro shares the endpoint/shape).

## Sources
- [Seedance 2.0 official prompt guide interpretation (apiyi)](https://help.apiyi.com/en/seedance-2-0-prompt-guide-video-generation-camera-style-tips-en.html)
- [Higgsfield: Seedance 2.0 complete prompting guide](https://higgsfield.ai/blog/seedance-prompting-guide)
- [fal: Seedream v4.5 prompt guide](https://fal.ai/learn/devs/seedream-v4-5-prompt-guide)
- [Segmind: Seedream 4 prompt engineering](https://blog.segmind.com/mastering-seedream-prompt-engineering-guide/)
- [LTX Studio previsualization pipeline](https://ltx.io/blog/how-to-build-a-complete-pre-visualization-pipeline)
- [AI Magicx: long-form AI video character-consistency guide 2026](https://www.aimagicx.com/blog/long-form-ai-video-character-consistency-guide-2026)
- [Kittl: AI video character consistency workflow 2026](https://www.kittl.com/blogs/ai-video-character-consistency-workflow/)
- [MindStudio: AI film production workflow (character sheets as source of truth)](https://www.mindstudio.ai/blog/ai-film-production-workflow-claude-code-mcp)
- [Magic Hour: keeping characters consistent in AI video (2026)](https://magichour.ai/blog/how-to-keep-characters-consistent-in-ai-video)
