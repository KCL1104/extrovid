# Model upgrades — June 2026

Research + decisions for three model questions: (1) script generation model, (2) wan2.7-videoedit
for editing, (3) HappyHorse-1.0 vs Wan for video. Implemented in the same change set.

## 1. Script generation → Qwen3.7-Max

**Decision: adopted.** Script writing is the single most creative / long-form step in the
pipeline, so it now routes to Alibaba's flagship instead of the balanced default.

- `qwen_script_model = "qwen3.7-max"` (config) — only the **ScriptAgent** uses it; every other
  agent (brief / cast / clarify / storyboard / visual-dev / review / revise / director / source)
  keeps `qwen_model` (`qwen3.6-plus`).
- `get_model()` is now parametrized — `get_model(model_name)` overrides the default; the mock
  path ignores the id, so offline tests are unaffected.
- Qwen3.7-Max ("The Agent Frontier"): 1M context, flagship-tier creative writing + instruction
  following, ~7-15% lower latency than Qwen3.7-Plus. `enable_thinking` stays forced off in the
  factory (Qwen3 thinking mode rejects `tool_choice=required`, which PydanticAI uses for
  structured output).
- Cost note: Max is ~$2.50/M in, $7.50/M out vs Plus ~$0.40 / $1.60. Only the script step pays
  the premium; if cost matters more than polish, set `QWEN_SCRIPT_MODEL=qwen3.7-plus`.

## 2. wan2.7-videoedit for editing → already integrated, kept

The "do we need to add wan2.7-videoedit for editing" question resolved to **already present**:
`submit_videoedit()` (video_factory) → consumed by `generate_service.edit_*` (per-take
natural-language revision that preserves take lineage) → `ShotModel.VIDEOEDIT` enum → covered by
`tests/test_videoedit.py`. ReviewAgent even emits ready-to-run videoedit instructions. Wan 2.7
documents native NL video editing ("change backgrounds, modify lighting, alter a character's
outfit"), matching the integration. No new work needed; it is now also provider-aware (below).

## 3. HappyHorse-1.0 vs Wan → HappyHorse is now the DEFAULT video provider

**Research finding: HappyHorse-1.0 is quality-superior.** It ranks **#1 on the Artificial
Analysis Video Arena** (blind human preference): T2V Elo ~1333–1374, I2V ~1392–1410 — roughly
**+140 over Wan 2.6's ~1189**. It is an Alibaba model (15B params, Apache-2.0 + commercial),
with native joint audio synthesis, 7-language lip-sync, 1080p, and fast 8-step inference.

**Key fact (corrected): HappyHorse is on DashScope / Qwen Cloud**, not a separate API. It is
listed on the Qwen Cloud model marketplace and Alibaba Cloud Model Studio with the SAME
`video-synthesis` async endpoint and the SAME `DASHSCOPE_API_KEY` the pipeline already uses for
Wan. Confirmed model ids:
- `happyhorse-1.0-t2v` (text-to-video)
- `happyhorse-1.0-i2v` (image-to-video)
- `happyhorse-1.0-video-edit` (NL video editing: source video + 0–5 reference images)

Because it shares the DashScope transport, the integration is just a **model-id selector**, not a
new provider seam — no extra key, endpoint, or polling logic.

**Full mode parity.** HappyHorse exposes all four DashScope model ids the pipeline needs:
`happyhorse-1.0-t2v`, `happyhorse-1.0-i2v`, `happyhorse-1.0-r2v` (reference-consistency shots —
`character_id` / `reference_asset_ids`), and `happyhorse-1.0-video-edit`. No Wan fallback is
required for any mode.

### What shipped
- `VIDEO_PROVIDER` env flag: **`"happyhorse"` (default)** | `"wan"`, validated in config.
- `video_factory` routes BOTH providers through one DashScope transport (`_submit_dashscope` /
  `_submit_dashscope_edit` / `_poll_dashscope`); the flag only picks model ids via
  `_resolve_video_model(mode)`. The four public functions keep stable signatures, so
  `generate_service` and the reconciler are untouched.
- `USE_MOCK_VIDEO` still gates the offline mock for both providers; the full lifecycle is
  mock-tested under both (`tests/test_video_provider.py`): happyhorse t2v/i2v/r2v/video-edit
  routing and the `VIDEO_PROVIDER=wan` override.

### Live deploy
HappyHorse runs on the **existing** `DASHSCOPE_API_KEY` — no new credential. To go live just set
`USE_MOCK_VIDEO=false` (Railway already has the DashScope key). Resolution defaults to 720P;
HappyHorse also supports 1080P. To revert to Wan everywhere: `VIDEO_PROVIDER=wan`. The request
body reuses the existing (working) Wan DashScope shape since both share the endpoint; if a
HappyHorse-specific field differs (e.g. `watermark`, `seed`, `size` vs `resolution`), confirm
against a live key and adjust `_submit_dashscope`.

### Deliberately not adopted (yet)
HappyHorse's **native joint audio** could replace the separate TTS + ffmpeg mixing path, but that
reconciliation (the rough cut currently owns dialogue TTS + ducked music + voiceover mixing) is
out of scope here — the existing audio pipeline stays authoritative. Flagged as a future lever.

## Sources
- Qwen3.7 — [The Agent Frontier](https://qwen.ai/blog?id=qwen3.7); [Qwen 3.7 Plus vs Max benchmark](https://ofox.ai/blog/qwen-3-7-plus-vs-qwen-3-7-max-real-benchmark-2026/)
- HappyHorse-1.0 — [Qwen Cloud model marketplace](https://www.qwencloud.com/models?output=video&sort=newest); [Alibaba Cloud: HappyHorse video-edit API](https://www.alibabacloud.com/help/en/model-studio/happyhorse-video-edit-api-reference); [Alibaba reveal (CNBC)](https://www.cnbc.com/2026/04/10/alibaba-happyhorse-ai-video-model-benchmark-reveal.html); [GitHub](https://github.com/CalvintheBear/HappyHorse-1.0)
- Wan 2.7 / DashScope — [DashScope video-synthesis API reference](https://www.alibabacloud.com/help/en/model-studio/text-to-video-api-reference)
