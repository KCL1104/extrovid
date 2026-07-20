---
title: "One prompt in, a finished film out: building an AI director on Qwen Cloud"
published: false
description: "How extrovid turns a single line of text into an edited short — with every model call, from script to final video, running on Alibaba's Qwen Cloud (DashScope)."
tags: ai, qwen, alibabacloud, video
# cover_image: replace with a screenshot of the architecture diagram (docs/architecture.html)
---

I've been building **[extrovid](https://www.extrovid.xyz)** — an AI-native director and editor. You give it one line of text, and it does the rest: it writes the brief and script, casts a consistent cast, develops a look, boards the shots, generates and reviews the video, adds voiceover, and hands you an edited rough cut. One prompt to a finished short, with a director you can talk to at every step.

The interesting part isn't any single model. It's that **every creative decision in the pipeline is made by a model on Qwen Cloud (Alibaba DashScope)** — the LLM that writes the script, the model that draws each frame, the voice that narrates, and the model that renders the video. This post is a tour of how those pieces fit together.

## The whole crew is a Qwen model

extrovid is built like a film crew, and every role is played by a model on Qwen Cloud:

| Job on set | Model on Qwen Cloud |
|---|---|
| Writing the script | `qwen3.7-max` — the flagship, for the one output that carries the whole film |
| Every other agent (brief, cast, look-dev, storyboard, director, review) | `qwen3.7-plus` — cheaper, huge context, used everywhere else |
| Concept frames, storyboard keyframes, cast portraits | `wan2.7-image-pro` (up to 4K) |
| Voiceover | `qwen3-tts` |
| Rendering the shots | **HappyHorse** or **Wan 2.7** (text-, image-, and reference-to-video) |

Six model families, four modalities — text, image, voice, and video — all reached through **one API key and one endpoint**. That single-vendor coherence turned out to be a real advantage: no juggling five providers, five billing accounts, and five sets of quirks. One key, one place to reason about cost, one place to reason about latency.

## Talking to Qwen: one endpoint, typed answers

DashScope exposes an **OpenAI-compatible endpoint**, which means the planning agents can speak to Qwen through the same tooling the rest of the ecosystem already uses. On top of that, extrovid uses a typed agent framework, so the models don't just return prose — they return **structured, validated data**: a script with numbered scenes, a cast list with consistent character descriptions, a storyboard as machine-readable shots. The brief becomes the script, the script becomes the cast, the cast becomes portraits — each stage's structured output feeds the next.

That structure is what lets the pipeline be a real pipeline instead of a pile of chat prompts. And it's why the planning phase can stream back to the UI **token by token**, stage by stage, so you watch the film get planned in real time rather than staring at a spinner.

One integration lesson worth passing on: Qwen3 models run in a "thinking mode" by default that's excellent for reasoning, but it conflicts with the strict "you *must* return this exact schema" mode that structured-output frameworks rely on. Turning thinking mode off for the planning agents made their output deterministic and reliable. If you're getting Qwen to emit strict JSON or tool calls, that's the knob to reach for.

## Images and voice

Once the plan exists, it needs to become something you can see and hear. `wan2.7-image-pro` draws the visual world — cast portraits so a character has a face, look-development frames so the film has a mood, and a keyframe for every shot in the storyboard. Because the Wan 2.7 image family handles both generation and editing, refining a frame later is the same kind of call, not a bolt-on service. Voiceover comes from `qwen3-tts`, one narration line per shot.

## Video: the slow, interesting part

Video is where the integration gets genuinely interesting, because rendering a shot isn't instant — it takes minutes. Qwen Cloud handles this the right way: it's **asynchronous**. You submit a shot, get a ticket back immediately, and check on it until it's ready. That shape influences the whole backend, which has to track jobs in flight, notice when they finish, and stream live progress to the UI as each shot lands.

A few things I'm especially happy with here:

- **Two video models, one path.** extrovid can render on **HappyHorse** (an Alibaba model that currently ranks #1 on the Artificial Analysis Video Arena, with native audio and multi-language lip-sync) or fall back to **Wan 2.7** — a single config switch, because both live on the same Qwen Cloud transport. No second integration.
- **Best-of-N with an AI "dailies" review.** Each shot is rendered several times, and a Qwen model reviews the takes and picks the winner automatically — the way a director watches dailies and chooses. You see it happen as a little status note: *"picked best of 3."* The machine owns the quality-control work, not just the generation.
- **Continuity that actually holds.** Each shot is seeded with the previous shot's final frame and the cast portraits, so a character's face and the film's look carry across clips that were generated independently. Continuity turns out to be an architecture problem, not a prompting one.

The one hard-won operational lesson: asynchronous results don't wait for you forever. A finished video's download link expires, so the backend has to fetch it and re-host it in your own storage promptly — otherwise you've paid to generate something you can no longer retrieve. Planning for "fetch and keep" from the start saved a lot of pain.

## The trick that made all of this pleasant to build

Every model in extrovid sits behind a **provider seam** — a thin boundary where a single setting decides whether a call hits real Qwen Cloud or a fast, deterministic offline stand-in. Flip one flag and the exact same pipeline runs with no key, no network, and no cost.

This one decision paid for itself over and over:

- **The whole thing is testable offline.** The full idea-to-cut pipeline runs in tests with zero spend, because every model has an offline counterpart behind the same boundary.
- **Iterating is free.** Image and video generation are billable; developing against the offline stand-ins (plus per-user daily caps in production) keeps costs bounded until you actually want pixels.
- **Going live is a config change, not a rewrite.** The offline and real providers are interchangeable, so switching to production Qwen Cloud is flipping a flag and adding a key.

If you take one thing from this post, let it be that: when you build on a paid, multi-modal cloud, build the seam that lets you also run without it. It's the cheapest thing you'll build and the one that lets you move fastest.

## Wrapping up

extrovid is an attempt to close the gap between "a model can make a shot" and "a tool can make a film" — the brief, the casting, the continuity, the take selection, the cut. Qwen Cloud made that feasible for a small project: one vendor covering text, image, voice, and video, reachable through one key, coherent enough that a single person could wire the whole crew together.

If you're building anything multi-modal for this hackathon, Qwen Cloud is a genuinely strong foundation to build the whole pipeline on — not just one piece of it.

*Built with Qwen Cloud / Alibaba DashScope end to end.*
