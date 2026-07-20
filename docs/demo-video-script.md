# extrovid — demo video (~2 minutes, interface tour)

**Format:** a calm walkthrough of the interface. You don't run a live generation — you tour the studio on a project that's already finished, explain what each part does, and then hand it to the judges to try themselves.

Two parts:

1. **[分鏡腳本 · Shot script](#part-1--分鏡腳本shot-script)** — what to show on screen, beat by beat.
2. **[旁白稿 · Voiceover manuscript](#part-2--旁白稿voiceover-manuscript)** — the words to read into the mic.

**Spec:** ~2:00 · 1920×1080 · dark theme · calm, specific narration (sentence case, no hype). Have **one completed project open** so every pane is already full of real content — no waiting on screen.

---

## Part 1 · 分鏡腳本（Shot script）

| # | TIME | ON SCREEN | ON-SCREEN LABEL |
|---|------|-----------|-----------------|
| 1 | **0:00–0:15** | Landing / studio fades up — dark "golden-hour" look, serif wordmark **extro**_vid_. Slow push toward the workspace. | `extrovid` · *one line in, a finished film out* |
| 2 | **0:15–0:40** | Open a **finished project**. Show the composer with its one-line prompt, then the **plan panel**: brief, script, cast, look, storyboard already filled in. Scroll the script gently. | `qwen3.7-max` (script) · `qwen3.7-plus` (agents) |
| 3 | **0:40–1:05** | The **board** — the storyboard with a keyframe per shot, and the rendered shots. Hover a shot: the *"picked best of 3"* chip; hover a keyframe: the *"chained for continuity"* chip. | `wan2.7-image-pro` · `HappyHorse` (video) |
| 4 | **1:05–1:25** | **Cast** panel (consistent character portraits) and **look** board (concept frames). Click a shot to open the **inspector** — the shot's details on the right. | *amber = your intent · cyan = the machine* |
| 5 | **1:25–1:45** | Open **Director chat** — show an example note like *"make shot 3 warmer."* Then the **cut / timeline**: the finished short plays with captions and voiceover. | `qwen3-tts` (voice) · *rough cut* |
| 6 | **1:45–2:00** | The **public gallery** of finished shorts. End on the wordmark with a short invite to try it. | *try it yourself →* [your URL] |

---

## Part 2 · 旁白稿（Voiceover manuscript）

Read straight down, block by block. ~150 words/min; leave a beat of silence between blocks.

---

**[0:00 – 0:15] · open** *(~34 words)*

> This is extrovid — an AI-native director and editor. You give it one line, and it takes you all the way to a finished, edited short. Let me show you around the studio.

---

**[0:15 – 0:40] · the plan** *(~58 words)*

> It starts with a single prompt. From that, extrovid writes the brief and the script, casts the characters, and develops the look — everything you see in the plan panel here. The script runs on qwen3.7-max; the rest of the crew runs on qwen3.7-plus. Every one of them is a model on Qwen Cloud.

---

**[0:40 – 1:05] · the board** *(~56 words)*

> This is the board — a keyframe for every shot, and the rendered shots beside them. Frames come from wan2.7-image-pro; the video is rendered on HappyHorse. Each shot is generated several times, and an AI review picks the best take — "best of three." Keyframes chain forward, so the look and the faces stay consistent.

---

**[1:05 – 1:25] · cast, look, inspector** *(~44 words)*

> Consistency is the hard part, so it's built in — one cast, held across every shot, and a single look developed up front. Amber is your intent; slate-cyan is the machine working. Click any shot to open its inspector on the right.

---

**[1:25 – 1:45] · direct & cut** *(~46 words)*

> And you can direct it in plain language — "make shot three warmer," and it re-renders just that shot. Voiceover is qwen3-tts, and the rough cut assembles itself: captions burned in, music ducked under the voice. Here's the finished short.

---

**[1:45 – 2:00] · try it** *(~34 words)*

> Everything you've seen runs on Qwen Cloud, end to end. Published shorts land in the gallery — and the best way to feel it is to try it yourself. Go ahead: give it one line.

---

*Total narration ≈ 272 words over ~2:00 — a relaxed pace with room to breathe.*

---

## Quick checklist

- **Have one finished project open before you record** — plan, board, cast, look, and the final short all populated. No generation runs on screen.
- **Point at the clever bits on screen:** the *"picked best of 3"* chip, the *"chained for continuity"* chip, the consistent cast.
- **Say "Qwen Cloud" a couple of times**, and let the model-id labels show on screen (`qwen3.7-max`, `qwen3.7-plus`, `wan2.7-image-pro`, `HappyHorse`, `qwen3-tts`).
- **Dark theme, 1920×1080, high bitrate** so the golden-hour gradients and small labels stay crisp.
- **End on the invite** — judges will use it live, so the last line hands it to them: *"give it one line."*
