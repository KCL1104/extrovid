# extrovid — demo video (3 minutes)

**Format:** screen-recording walkthrough of the live product, with voiceover.
**Golden rule:** every screen shown is the *real* product; every model call runs on Qwen Cloud / Alibaba DashScope — say so, and show the model ids on screen.

This doc has two parts:

1. **[分鏡腳本 · Shot script](#part-1--分鏡腳本shot-script)** — the timeline: what to capture, what to click, what to caption on screen.
2. **[旁白稿 · Voiceover manuscript](#part-2--旁白稿voiceover-manuscript)** — the clean, continuous narration to read into the mic.

Plus a [production checklist](#production-checklist) at the end.

**Spec:** ~3:00 total · 1920×1080 @ 60fps · dark theme only (the product is dark-only by design) · one warm, restrained music bed, ducked hard under every line of VO. Tone: calm, specific, sentence case — a director talking quietly on a calm set, never an ad.

---

## Part 1 · 分鏡腳本（Shot script）

| # | TIME | ON SCREEN — capture / click | ON-SCREEN CALLOUT (lower-third / label) |
|---|------|-----------------------------|------------------------------------------|
| 1 | **0:00–0:18** | Cold open. Landing page fades up — dark "director's studio at golden hour," lowercase serif wordmark **extro**_vid_. Slow push toward the composer; a one-line prompt sits waiting in the field. | Title card: `extrovid` · small line beneath: *one line in, a finished film out* |
| 2 | **0:18–0:38** | Sign in with Google (one tap). Land on the workstation — three panes: **plan · board · inspector**. Click **new project**. In the composer, type live: *"A lighthouse keeper who befriends a storm. Warm, hopeful, 30 seconds."* Press the amber **start** button. | Lower-third: *amber = your intent · cyan = the machine working* |
| 3 | **0:38–1:05** | Planning streams in as one call. Agent-trace rows appear top-to-bottom: *directing… briefing… writing script… casting… developing the look… boarding.* Brief writes itself **token by token**, then the script, scene by scene. | Label the rows: `qwen3.7-plus` on brief/cast/look/board · `qwen3.7-max` on the script row |
| 4 | **1:05–1:30** | Image generation. Cast panel fills with **portraits**. Look-dev shows **concept frames** (golden light, storm-grey sea). Storyboard fills with **keyframes**, one per shot. Hover a keyframe → chip: *"chained from previous frame for continuity."* | Label: `wan2.7-image-pro · up to 4K` |
| 5 | **1:30–2:00** | Trigger video. Shot cards flip to **rendering**; SSE progress bars move live; a queue shows shots lined up; the **pre-spend cost meter** reads before spend. Trace chip animates: *"rendering take 1 of 3… checking continuity… picked best of 3."* Winning take snaps in. | Label: `HappyHorse · #1 Artificial Analysis Video Arena · on DashScope` |
| 6 | **2:00–2:22** | Voiceover + assembly. A **voiceover track** appears under the timeline. Rough-cut assembly runs: **burned-in captions**, **music ducking** under the narration. The finished short plays inline — lighthouse, storm, warm resolve. | Label: `qwen3-tts` → then `rough cut · captions + ducked music` |
| 7 | **2:22–2:42** | Open **Director chat**. Type: *"make shot 3 warmer."* Director replies in sentence case, re-renders **only shot 3**, and the warmer take drops into the timeline. Play the updated cut. | Lower-third: *revise · retry · recast · reorder — in plain language* |
| 8 | **2:42–3:00** | Click **publish** → the short lands in the public gallery. Cut back to the finished frame. Quiet overlay: *every model on Qwen Cloud · also runs fully offline via the mock seam.* End on the wordmark. | End card: `extrovid` · *that's a take.* |

---

## Part 2 · 旁白稿（Voiceover manuscript）

Read straight down, block by block, matching the timecodes. Pacing sits at ~150 words/min; leave ~1 second of silence at each hand-off so each beat lands. Don't rush the last line — let **"Print it."** breathe.

---

**[0:00 – 0:18] · cold open** *(~46 words)*

> This is extrovid. You give it one line. It gives back a finished, edited short — it writes the brief and script, casts the characters, develops the look, boards the shots, renders them, adds voiceover, and cuts it together. Every model it calls runs on Qwen, on Alibaba Cloud.

---

**[0:18 – 0:38] · sign in & the one input** *(~48 words)*

> Sign in, create a project, and write the idea in plain language. That's the only creative input it needs. Amber is your intent; slate-cyan is the machine working. Press start — and the director takes it from here.

---

**[0:38 – 1:05] · planning streams in** *(~62 words)*

> Planning runs as a single call and streams straight back. Every row is an agent, and every agent is a Qwen Cloud model. The brief, the cast, the look, and the board run on qwen3.7-plus. The script — the flagship — runs on qwen3.7-max. You're watching it think, token by token. No spinner.

---

**[1:05 – 1:30] · it draws the world** *(~54 words)*

> Now it draws. Cast portraits, look-development concept frames, and a storyboard keyframe for every shot — all from wan2.7-image-pro, up to four K. And the keyframes chain forward, so the keeper's face and the film's look hold steady from one shot to the next.

---

**[1:30 – 2:00] · video, best of N** *(~70 words)*

> Press generate. The shots render through HappyHorse — number one on the Artificial Analysis video arena — also running on DashScope. It renders best of N: several takes per shot. Then an AI dailies review watches every take and picks the winner. "Picked best of three." Progress streams live, and the cost is shown before it spends a thing.

---

**[2:00 – 2:22] · voice & the cut** *(~44 words)*

> Voiceover is qwen3-tts. Then the rough cut assembles itself — captions burned in, music ducked under the voice. And there it is: a finished short. One line of text, a couple of minutes ago.

---

**[2:22 – 2:42] · talk to the director** *(~48 words)*

> Every step is a conversation. Tell the director, "make shot three warmer" — and it re-renders just that shot and slots it back into the cut. Revise, retry, recast, reorder — all optional, all in plain language, at any step.

---

**[2:42 – 3:00] · publish & payoff** *(~52 words)*

> Publish to the gallery, and it's done. Every model — script, cast, look, image, video, voice — runs on Qwen, on Alibaba Cloud. And the whole pipeline also runs offline, through a mock seam: deterministic, cost-safe, fully testable. One line, to a finished cut. That's a take. Print it.

---

*Total narration ≈ 424 words over ~3:00 — comfortably inside a 150-wpm delivery with room to breathe between beats.*

---

## Production checklist

**Pre-generate everything.** Record against a project that has already completed a full run end to end — real video renders take minutes and will stall a live demo. Have ready: the finished short, all takes, portraits, keyframes, the voiceover track, and the published gallery entry. You're *replaying* a real run, not gambling on one.

**Keep it honest.** Capture the *real* token-streaming and SSE progress once, then trim so each beat lands inside its time block. Never fake the UI — every screen must be the actual product.

**The one thing you can run live (optional):** the Director chat "make shot 3 warmer" revision reads best if it's genuinely quick. If it can't finish in ~10 seconds, pre-bake the warmer take and scrub to it.

**Make the clever bits visible, not just spoken.** Linger ~1 second on each of: the *"picked best of 3"* chip, the *"chained for continuity"* chip, and the **pre-spend cost meter**. A judge scanning for the differentiators should catch them on screen.

**Name Qwen Cloud on screen and in voice.** Say "Qwen Cloud / DashScope" at least three times (cold open, planning, video). Show the model ids where they appear via a lower-third or the inspector label: `qwen3.7-max` on the script row, `qwen3.7-plus` on the other planning agents, `wan2.7-image-pro` on the keyframes, `HappyHorse` on the shots, `qwen3-tts` on the voiceover track.

**Capture & export:** 1920×1080 @ 60fps, dark theme only, high bitrate so the golden-hour gradients and small trace-chip text stay crisp.

**Audio:** one warm, restrained music bed at golden-hour temperature, ducked hard under every line of narration so the words always win. Record the VO in one calm take per block; breathe between blocks.

**Sample prompt used in the demo:** *"A lighthouse keeper who befriends a storm. Warm, hopeful, 30 seconds."* — swap for whatever you have a clean pre-generated run of.
