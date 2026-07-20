---
title: "One prompt in, a finished film out: running an entire AI video pipeline on Qwen Cloud"
published: false
description: "How we wired every model call in an AI director/editor — script, images, voice, and video — to Alibaba's Qwen Cloud (DashScope) behind a single provider seam, and the integration gotchas we hit along the way."
tags: ai, python, qwen, alibabacloud
# cover_image: replace with a screenshot of the architecture diagram (docs/architecture.html)
---

I've been building **[extrovid](https://www.extrovid.xyz)** — an AI-native director and editor. You give it one line of text, and it writes the brief and script, casts a consistent cast, develops a look, boards the shots, generates and reviews the video, adds voiceover, and hands you an edited rough cut. One prompt to a finished short.

The interesting engineering story isn't any single model — it's that **every model call in the pipeline runs on Qwen Cloud (Alibaba DashScope)**, from the LLM that writes the script to the model that renders the video, all behind one seam that lets the whole thing also run offline for free. This post is about that integration.

Here's the pipeline, and which Qwen model does each job:

```
idea → brief → script → cast → look-dev → storyboard → shots → voiceover → rough cut → publish
```

| Stage | Model on Qwen Cloud |
|---|---|
| Script writing | `qwen3.7-max` (the flagship) |
| Every other agent (brief, cast, look-dev, storyboard, clarify, revise, director, review) | `qwen3.7-plus` |
| Images (concept frames, keyframes, portraits) | `wan2.7-image-pro` (up to 4K) |
| Image edits | `wan2.7-image-pro` (unified gen + edit) |
| Voiceover | `qwen3-tts` |
| Video (t2v / i2v / r2v / edit) | **HappyHorse** or **Wan 2.7** |

Six model families, four modalities, one API key. Let me show you how it's wired.

## The core idea: one provider seam, mock ⇄ real

Before any model integration, I made one architectural decision that paid for itself ten times over: **every model call goes through a provider "seam" gated by a `USE_MOCK_*` flag.** Flip the flag and the exact same call either hits real Qwen Cloud or a deterministic offline mock.

Here's the entire LLM seam:

```python
# app/providers/model_factory.py
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.alibaba import AlibabaProvider

def get_model(model_name: str | None = None) -> Model:
    settings = get_settings()
    if settings.use_mock_llm:
        # deterministic mock — no network, no key, no cost
        return FunctionModel(dispatch_mock, stream_function=dispatch_mock_stream)

    return OpenAIChatModel(
        model_name or settings.qwen_model,
        provider=AlibabaProvider(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        ),
        settings=OpenAIChatModelSettings(extra_body={"enable_thinking": False}),
    )
```

Two things worth calling out:

1. **PydanticAI ships an `AlibabaProvider`.** DashScope exposes an OpenAI-compatible endpoint (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`), so you get typed, schema-validated agent outputs from Qwen with almost no glue code. Every agent — brief, cast, storyboard, director — is a `pydantic_ai.Agent` whose model comes from `get_model()`.

2. **`model_name` is an override.** The script agent routes to the flagship `qwen3.7-max` (worth the cost for the one output that carries the whole film), while the dozen other agents use the cheaper, 1M-context `qwen3.7-plus`. Same seam, different model id.

Because the mock path is deterministic, the **entire pipeline runs offline** — which is how ~236 backend tests run with no key and no spend. More on why that matters at the end.

## Gotcha #1: Qwen3 "thinking mode" vs. structured output

This one cost me an afternoon, so here's the fix up front. See that `enable_thinking: False` in the snippet above?

PydanticAI gets structured output by forcing a tool call — it sends `tool_choice=required` under the hood so the model *must* return your schema. But **Qwen3 models run in "thinking mode" by default, and thinking mode rejects `tool_choice=required`.** You get an API error instead of a clean parse.

The fix is one line in `extra_body`:

```python
settings=OpenAIChatModelSettings(extra_body={"enable_thinking": False})
```

Disable thinking mode and structured planning becomes deterministic and reliable. If you're pairing Qwen3 with any framework that leans on forced tool calls for JSON output (PydanticAI, Instructor, etc.), this is the setting you're looking for.

## Images and voice: the multimodal-generation endpoint

Concept frames, storyboard keyframes, and cast portraits all come from `wan2.7-image-pro` on DashScope's synchronous multimodal-generation endpoint. The seam is the same shape — a `USE_MOCK_IMAGE` flag swaps in a tiny valid PNG so the image flow is testable offline:

```python
# aspect ratio → pixel size, accepted by wan2.7-image-pro on DashScope
_SIZE_BY_ASPECT = {
    "9:16": "928*1664",
    "16:9": "1664*928",
    "1:1":  "1328*1328",
    "4:5":  "1140*1472",
}
```

Voiceover works identically through `qwen3-tts`, gated by `USE_MOCK_TTS` (the mock returns decodable silent WAV bytes so ffmpeg can still mix a test cut). One nice property of the Wan 2.7 image family: generation and editing are unified, so refining a frame is a drop-in model call rather than a separate service.

## Video: the async submit → poll transport

Video is where the integration gets more interesting, because video generation is **slow** — you don't get a response in one request. DashScope's video-synthesis API is asynchronous: you submit a job, get a `task_id` back immediately, then poll for the result.

The magic header is `X-DashScope-Async: enable`:

```python
def _dashscope_async_headers(settings):
    return {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

async def _submit_dashscope(settings, model, mode, prompt, ...):
    body = {"model": model, "input": {"prompt": prompt}, "parameters": params}
    resp = await request_with_retry(
        "POST", settings.dashscope_video_url,
        headers=_dashscope_async_headers(settings), json=body, timeout_sec=60,
    )
    resp.raise_for_status()
    return SubmitResult(task_id=resp.json()["output"]["task_id"], model=model)

async def poll_video(task_id: str) -> PollResult:
    # GET /api/v1/tasks/{task_id} → PENDING | RUNNING | SUCCEEDED | FAILED
    ...
```

One seam, two providers. The `VIDEO_PROVIDER` flag chooses between **HappyHorse** (default — an Alibaba model that ranks #1 on the Artificial Analysis Video Arena, with native audio and 7-language lip-sync) and **Wan 2.7**. Both ride the *same* submit→poll transport and the *same* `DASHSCOPE_API_KEY`; the flag only maps abstract modes (t2v / i2v / r2v / edit) to model ids:

```python
def _resolve_video_model(settings, mode):
    if settings.video_provider == "happyhorse":
        return {"t2v": "happyhorse-1.1-t2v", "i2v": "happyhorse-1.1-i2v",
                "r2v": "happyhorse-1.1-r2v", "videoedit": "happyhorse-1.0-video-edit"}[mode]
    return {"t2v": "wan2.7-t2v", ...}[mode]
```

The mode is inferred from what you hand it: references → r2v, a first frame → i2v, prompt only → t2v. That r2v/i2v path is what gives us **keyframe-first continuity** — each shot inherits the previous shot's last frame as a seed, so a character's face and the film's look hold across independently generated clips.

We also generate video **best-of-N**: several takes per shot, then an AI "dailies" review picks the winning take automatically. The whole editorial decision happens server-side and surfaces in the UI as a little trace chip — *"picked best of 3."*

## Gotcha #2: async jobs need a reconciler (and it has opinions)

Submit→poll means you can't just `await` a video. Something has to keep polling `RUNNING` jobs until they finish, then download and re-host the result. That's a background reconciler loop, started in the FastAPI lifespan:

```python
async def _reconciler_loop():
    interval = get_settings().video_reconcile_interval_sec
    while True:
        await asyncio.sleep(interval)
        try:
            async with SessionLocal() as session:
                await reconcile_running(session)   # poll + ingest finished jobs
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("reconciler iteration failed; continuing", exc_info=True)

@asynccontextmanager
async def lifespan(app):
    task = None
    if not settings.use_mock_video:          # only run against real Qwen Cloud
        task = asyncio.create_task(_reconciler_loop())
    yield
    if task:
        task.cancel()
```

Two hard-won lessons live in that snippet:

- **It's in-process with no leader election, so it must be pinned to a single instance.** If you run two backend replicas, you get two reconcilers double-polling every job — duplicate DashScope calls, state races, wasted spend. This one detail shapes the whole deployment topology (single always-on instance; only the frontend scales horizontally).
- **DashScope result URLs expire in ~24 hours.** The reconciler *must* download the bytes and re-upload them to your own object storage inside that window, or the asset is gone and you're paying to regenerate it. "Download-then-rehost" isn't optional — it's the contract.

Also note the guard: the reconciler only starts when `use_mock_video` is false. Offline, there are no async jobs to reconcile, so the loop stays dormant — the seam again.

## Why the seam was worth it

Wiring everything through one mock⇄real seam gave me three things that made the Qwen integration genuinely pleasant to build on:

1. **Offline, deterministic tests.** The full idea→cut pipeline runs in CI with zero network and zero cost, because every provider has a deterministic mock behind the same interface.
2. **Cost safety while iterating.** Video and image generation are billable; developing against mocks (plus per-user daily caps in production) keeps spend bounded. You flip to real Qwen Cloud only when you actually want pixels.
3. **One code path to production.** The mock and the real provider satisfy the *same* function signatures, so "make it real" is an env change, not a rewrite. `USE_MOCK_LLM=false`, add `DASHSCOPE_API_KEY`, done.

## Takeaways if you're integrating Qwen

- **Use the OpenAI-compatible endpoint.** `dashscope-intl.aliyuncs.com/compatible-mode/v1` + PydanticAI's `AlibabaProvider` gives you typed agents with almost no glue.
- **Set `enable_thinking: False` when you need forced-tool structured output** from Qwen3.
- **Pick the right tier per call.** `qwen3.7-max` for the one output that carries the product; `qwen3.7-plus` (cheaper, 1M context) for everything else.
- **Treat video as async from day one.** `X-DashScope-Async: enable`, a single-instance reconciler, and download-then-rehost before the 24h URL expiry.
- **Build the mock seam first.** It's the cheapest thing you'll build and the one that lets you move fast against a paid, multi-modal cloud.

extrovid is open source and the whole pipeline runs offline out of the box (`USE_MOCK_*=true` by default), so you can clone it, read the seams, and flip on the ones you want to see live. If you're building anything multi-modal on Qwen, I hope the patterns above save you the afternoon they cost me.

*Built with FastAPI + PydanticAI, Next.js, and Qwen Cloud / Alibaba DashScope end to end.*
