# Frontend redesign — "Board Room" (Direction B)

> **P1 IMPLEMENTED + build-green 2026-06-21** (uncommitted on `main`) — token/primitive pass:
> surface-ladder (`--color-elevated`/`--color-hairline`/halos/`--glow-hero`) + slate-cyan
> machine-state (`--color-run` repointed amber→cyan; warnings reassigned to amber so only genuine
> running/live states turned cyan); 4 `shadow-2xl` → `ring`/`bg-elevated`; `.title` `-0.02em`, body
> tracking 0, grain `0.025`, vignette softened, `.rise` `0.38s`; `Panel` hover/selected + `Skeleton`
> + `Button` `size`/press-spring; ShotCard running cell now a cyan shimmer skeleton, not a bare
> spinner. `tsc` + `eslint` + `next build` all clean.

> **P2 IMPLEMENTED + build-green 2026-06-21** (uncommitted on `main`) — workspace re-shell:
> `Workspace.tsx` rebuilt as a three-zone editing room — left **`StageRail`** (new vertical pipeline
> map, desktop) / horizontal `Tabs` (mobile) for the 6 stages; center **canvas** (board is the
> default hero); right **persistent Director rail** (collapsible, shows the inspected shot when one
> is selected, else the Director — mobile = drawer via a header button); **`QueueDock`** footer
> replaces the Queue tab. Number keys now jump the 6 stages. All existing state / SSE / 5s-poll /
> handlers / panels untouched (pure re-composition). `tsc` + `eslint` + `next build` all clean.

> **P3 IMPLEMENTED + build-green 2026-06-21** (uncommitted on `main`) — Director-rail streaming:
> new **`StepTrace`** renders the director's `tool_start`/`tool_result` SSE events as live mono step
> rows (cyan pulse while running → ok ✓ / fail "retry"), replacing the bare "directing…" spinner —
> genuinely live (one row per real tool call). New **`AgentMessage`** extracts the chat bubble and
> reveals the newest assistant reply with a client-side typewriter + cyan caret (respects
> `prefers-reduced-motion`; skips replies > 600 chars). `DirectorPanel` rewired: `liveTools[]` →
> `liveSteps[]` (status-tracked).
>
> **P3.1 — REAL token streaming (shipped, replaces the client-side typewriter):** the backend
> `/director/stream` now streams the model-request node's text deltas as `text_delta` SSE frames
> (PydanticAI `is_model_request_node` + `PartDeltaEvent`/`TextPartDelta`; Qwen OpenAI-compatible AND
> the mock `dispatch_mock_stream` both support it). `DirectorPanel` accumulates `text_delta` into a
> live bubble with a cyan caret; `done` finalizes it. `test_streaming` uses a streamable
> `FunctionModel` and asserts `text_delta`. **Full backend pytest + frontend tsc/eslint/build green.**
>
> **Remaining honest note:** the board shows *which shots are working* via the separate job-progress
> SSE (`/events` → cyan shimmer, P1); a director **step→specific-card** highlight stays deferred
> (director tool events still carry no `shot_id` — a small future backend add).
>
> **Committed + pushed 2026-06-21:** `e3619f2` on branch `redesign/board-room` (P1+P2+P3+P3.1).
>
> **P4 IMPLEMENTED + build-green 2026-06-21** (uncommitted) — select-to-scope + Cast chips:
> ⌘/Ctrl/Shift-click a board card (or its new "◎ direct" button) pins an `@shot N` chip into the
> Director input — ⌘-click several to batch-scope; new `CastChip` makes each cast member a clickable
> chip that pins `@Name`. Scoped items show an amber ring (board) + chips (Director); sending
> prepends a natural-language scope prefix ("Regarding shot 4, the character Mei: …") — the agent
> already understands shot/cast references, so **no backend change**. Toggling scope surfaces the
> Director (closes the inspector, expands the rail); sending clears the scope. `tsc`/`eslint`/`build`
> green. **Deviations from the spec sketch:** plain click still opens the inspector (scope is the
> modifier-click / "◎ direct" button), and cast injection is click-to-pin, not drag-and-drop (DnD
> deferred). **Next: P5 (Sequence/Timeline altitude toggle + VariationGrid A/B compare).**

> **Status (2026-06-21): DESIGN LOCKED.** Direction chosen after a 6-category
> competitive study (oiioii.tv, AI-video SaaS, AI-coding SaaS, pro video tools, AI-native craft,
> agentic chat-canvas). Decisions locked with the owner:
> **(1) Direction B "Board Room"** — board-first canvas + co-equal Director rail;
> **(2) add one cool machine-state tone** (slate-cyan) alongside amber — see `brand.md`;
> **(3) docs first, then code.** This is the executable spec; the brand evolution lives in
> `/brand.md`.

> **TL;DR** — Stop treating the pipeline as eight tabs you click *through*. Promote the
> storyboard to an always-present **hero canvas** (the deterministic spine / source of truth),
> demote the eight stages to a thin left **progress map**, and graduate the Director agent from
> one buried tab to a **persistent co-equal right rail** that reads and writes the board.
> Everything the backend needs already exists — this is mostly a **front-end recomposition** of
> `Workspace.tsx`, not new pipeline work. Keep the golden-hour / serif / mono soul; earn the
> "AI-native" claim with streaming states, visible agent traces, surface-ladder depth, spring
> motion, and a ⌘K spine.

---

## 0. Why this direction (the research in one paragraph)

Six independent research lenses converged on the same answer to extrovid's central open
question ("keep linear staged tabs vs. move to an agent-canvas"): the winning 2026 pattern is a
**deterministic board/timeline as the map and source of truth, with the agent as a co-equal pane
that operates on it**, plus inline per-object steering. Pure chat-as-pipeline loses spatial
orientation ("where am I in the 8 shots?") and feels lossy; pure tabbed-stage navigation feels
un-agentic and buries the product's leverage — which is exactly extrovid's situation today, where
`Director` is one tab among eight. The anchor reference **oiioii.tv** is essentially extrovid's
concept-twin (user = Director, a named crew, a staged pipeline, dark cinematic), which both
**validates** the bet and tells us the **differentiation lever**: oiioii's top complaints are
cross-stage visual-consistency drift, anime-only scope, and a 60s cap — exactly where extrovid's
continuity machinery (batons, keyframe-first chaining, cast portraits, best-of-N) and ~20-min
length tiers win. Lead with continuity; don't replicate a chat that loses the thread.

Extrovid already owns the **rare half** of the premium bar (warm near-black + a real serif +
mono-as-crew-language + grain — almost nobody in AI-video has a serif or a warm palette). The gap
is **execution discipline**, not identity: surface-ladder depth instead of borders, streaming /
agent-trace visual language instead of bare spinners, spring motion, and a ⌘K spine.

---

## 1. Design principles (the bar we're hitting)

1. **The artifact is the hero; chrome recedes.** The generated frames/board own visual
   attention. Sidebars dim, the stage map is quiet, the Director rail is co-equal not dominant.
   (Linear "structure felt not seen.")
2. **Board is the map; the agent operates on it.** Never make the Director chat the only way to
   navigate. The board stays clickable; the agent reads/writes it.
3. **Direct manipulation AND natural language, switchable anytime.** Click a shot to edit it
   inline; or talk to the Director. Bimodal steering (v0 Design Mode / Lovable Visual Edits).
4. **Make agency legible.** Tool-events, best-of-N, continuity review render as visible step
   traces — "checking continuity… picked best of 3" — not hidden machinery behind a spinner.
5. **Never a bare spinner for AI work.** Token-by-token streaming + skeletons sized to the final
   frame + resolvable step chips.
6. **Depth from a lightness ladder, not shadows.** Warm near-black surfaces elevate one notch;
   hairlines and shadow-as-border rings only. (The single tell of 2026 vs 2021 dark UI.)
7. **One accent = human intent; one cool tone = machine working.** Amber for actions/focus/
   selection; slate-cyan for rendering/streaming/agent-in-progress. Nothing else colored in chrome.
8. **Cost before spend.** Per-shot estimate against the per-project budget shown *before* render.
9. **Generation-first, configuration-deferred.** Empty states are composers, not config forms.
10. **A11y is non-negotiable.** Keep focus-visible rings, `aria`, live regions, and the
    `prefers-reduced-motion` global override already in `globals.css`.

**Constraints (locked):** Next.js 16 / React 19 / Tailwind v4 `@theme` tokens / lucide-react.
**No Radix/shadcn/MUI.** Dark-only app. Read `node_modules/next/dist/docs/` before writing Next
code (see `frontend/AGENTS.md` — this Next has breaking changes).

---

## 2. Information architecture

### Global shell (`Shell` + `Sidebar`) — keep, make it recede
- **Sidebar recedes.** Today active rows use a full `bg-panel-hi` fill. Replace with a 2px amber
  left-edge bar + brightened text; dim inactive to `text-faint`. The rail is orientation, not a
  competing surface.
- **Add a ⌘K entry** pinned under "+ New project" (palette in §5). The sidebar stops being the
  only navigation.
- **Project rows become a cross-project HUD.** Add a mono micro-status (`3/8` + a cyan
  `pulse-dot` when jobs are in flight), reusing the `StatusBadge` idiom from `ShotBoard`.

### Landing (logged-out) — title-card + live composer
Keep the pipeline-as-pitch chip row (it's good and on-theme) but **lead with a title-card hero**:
one Instrument-Serif "now showing"-style line with the wordmark as a film slate, the accent word
animating (kinetic word-swap). Gallery teaser stays as social proof, **not** the primary surface
(avoid the Sora feed-as-product trap).

### Dashboard `/` — invert from config-first to generation-first
Today: a `title/aspect/duration` form + 2 recent cards. Change to:
- **One large amber-glow brief composer** — `"Describe the film you want to direct…"` + 2–3
  example-brief chips + a secondary **"import a long source."** (New `Composer`, §5.)
- **Intent tiles** beneath it (mode-first entry, from oiioii modes + Runway Apps):
  `Short clip · Narrative · Long-form (chaptered) · Import & revise`. Picking one pre-sets the
  **length tier + HITL profile** (today these live nowhere in the UI). Aspect/duration/budget move
  into a collapsible "advanced" row — not a gate.
- **Recent project cards** stay (they're good; keep the mono progress bar).

### Workspace `/projects/[id]` — the core change (§3).

### Gallery & Settings — light touch
- Gallery: grading-suite treatment — heavy black gutters, media is the only color.
- `SettingsModal`: keep structure; restyle onto the surface ladder + ring-not-shadow.

---

## 3. The Workspace layout (core proposal)

### Three-zone editing room

```
┌───────────────────────────────────────────────────────────────────────────┐
│ HEADER  ← back · status eyebrow · title · [aspect][dur][3/8 shots] · ⌘K · ⋯ │
├──────────┬───────────────────────────────────────────────┬─────────────────┤
│ STAGE    │  CANVAS  (hero artifact)                       │  DIRECTOR rail  │
│ MAP      │  ┌ altitude: [Board] [Sequence] [Plan] ┐       │  (co-equal,     │
│ (thin)   │  │                                      │       │   collapsible)  │
│ ①Brief   │  │  scene-banded board   (default)      │       │  agent thread   │
│ ②Script  │  │   ┌──┐→┌──┐→┌──┐→┌──┐                │       │  + StepTrace    │
│ ③Look    │  │   │s1│ │s2│ │s3│ │s4│  baton links    │       │  + composer     │
│ ④Cast    │  │   └──┘ └──┘ └──┘ └▓▓┘                │       │  [@shot 4 chip] │
│ ⑤Board ● │  │                                      │       │                 │
│ ⑥Cut     │  └──────────────────────────────────────┘       │                 │
│          │   selection → INSPECTOR docks as 3rd column ───  │                 │
│ ───────  │   (desktop) / Drawer (mobile)                   │                 │
│ Queue ▣  │                                                 │                 │
└──────────┴───────────────────────────────────────────────┴─────────────────┘
              QueueDock (thin footer: in-flight jobs, retryable failures)
```

### Zone roles

**Stage map (left, ~180px — was the sticky horizontal `Tabs`).**
The eight tabs become a vertical **progress map**: each stage is a row with done-✓ / live
`pulse-dot` / locked state — reuse `TabItem`'s existing `done/locked/live/divider` semantics. It
is a **map of one document**, not a screen-switcher: clicking a stage scrolls/filters the canvas
to that region and sets which inspector facets are relevant. Number keys 1–8 still jump. Collapses
to an icon rail below `xl`. This preserves the legible pipeline-as-pitch while killing the
"wizard tabs" feel the research flags as un-agentic.

**Canvas (center — the hero).**
Default = the **scene-banded board** (`ShotBoard`, already good). A quiet segmented **altitude
toggle** (Descript Storyboard↔Timeline / Resolve Cut↔Edit) switches the *same shot data* between:
- **Board** — current scene-banded filmstrip cards (`ShotBoard` as-is, + a `selected` ring state).
- **Sequence** — new low-density **`TimelineStrip`**: proportional-width shot blocks (width =
  duration), the continuation **baton drawn as a connector line** between adjacent blocks,
  render-state colored. This is the "storyboard↔timeline complement" the FE/BE review flagged as
  missing — and it **absorbs Direction C** as a mode rather than a separate product.
- **Plan** — the script/outline as an editable document (the review-gate artifact). A
  Preview/Code/Diff-style toggle where "Code" = the structured plan JSON, "Diff" = a proposed
  revision. `Look` surfaces as a previz strip above the board; `Cast` surfaces as the chip library.

**Director rail (right, ~360px — co-equal, collapsible).**
`DirectorPanel` graduates from one buried tab to a **persistent pane**. It already streams
`tool_start` events over SSE (`/projects/{id}/director/stream`) and resolves to a `done` event
with `reply` + `actions` + `state`. Two upgrades:
1. Render those events as the new **`StepTrace`** (§5) — collapsible step rows that auto-expand
   while running, auto-collapse on done — *not* the current flat `Wrench` pills.
2. **Each step highlights the affected shot card on the canvas** as it resolves (the step carries
   a `shotId`). The board becomes the progress bar.
Collapses to a thin amber tab on narrow screens / when the user wants the board full-width.

**Inspector (selection-driven 3rd column).**
Today `ShotInspector` is a 997-line monolith opened by clicking a card. Keep the dock, but:
- It sits **between canvas and Director rail**, empty until a shot is selected.
- It becomes **accordion-sectioned** (Premiere Properties-panel lesson):
  `Composition / Camera / Performance / Continuity / Acceptance / Takes`, collapsed by default —
  novices see the summary, pros expand depth.
- Below `lg` it remains the existing `Drawer`.
- A "fast mode" hides it entirely for batch board work (Resolve Cut page).

### How the five surfaces coexist (explicit answer)
| Surface today | Becomes |
|---|---|
| Staged pipeline (8 horizontal tabs) | **Left stage map** — a navigable progress map, not screens |
| Storyboard / board | **Canvas hero** with Board↔Sequence↔Plan altitude toggle |
| Shot inspector | **Selection-driven 3rd column**, accordioned (was a 997-line monolith) |
| Queue (a whole tab) | **`QueueDock`** — a thin expandable footer status strip |
| Director (a buried tab) | **Persistent right rail**, co-equal, operating on the board |

This is a **refactor of `Workspace.tsx`**: all existing state (versions / jobs / SSE / 5s poll /
`generating` set) is untouched; only the render tree changes from `tab === x && <Panel/>` to a
three-column grid where the canvas reads a `view` (`board`/`sequence`/`plan`) and the rails are
always mounted.

---

## 4. Brand / token changes (summary — full spec in `/brand.md`)

The redesign rides on an evolved token set. The load-bearing changes to
`frontend/app/globals.css` `@theme`:

- **Surface ladder** — add a 4th warm near-black notch `--color-elevated: #2a2319` (popovers,
  dragged shot, active take). Depth = lightness + hairline, **never `shadow-*` on dark**. The two
  `shadow-2xl` uses (Drawer, ⋯ menu, delete modal) swap to `ring-1 ring-border-hi` + one notch.
- **One cool machine-state tone (NEW)** — `--color-live: #6fb3c4` (desaturated slate-cyan) for
  rendering / streaming caret / agent-trace-in-progress / queue pulse. **Repoint `--color-run`
  from amber → `#6fb3c4`.** Amber stays = human intent (action / focus / selected / wordmark).
  This is a tungsten-vs-daylight color-temperature story — authentically filmic.
- **Hairline overlay** — `--color-hairline: rgba(244,239,230,0.07)` replaces hard warm borders on
  cards.
- **Halos** — `--color-accent-glow` / `--color-live-glow` (≈15% alpha) for soft focus halos.
- **Hero-only glow** — promote the hardcoded `body` radial into `--glow-hero`, applied only to
  empty-state composers and render-complete moments; pull it off dense working surfaces.
- **Type** — `.title` tracking `-0.01em → -0.02em`; body `letter-spacing 0.01em → 0`.
- **Grain** — dial wrapper grain `0.035 → ~0.025` and scope it off the board/cast/inspector;
  soften vignette `#00000080 → #00000066` so thumbnails aren't crushed at the edges.
- **Motion** — `.rise` `0.6s → ~0.38s`; adopt spring physics for mounts/reorders/transitions;
  add `.stream-caret`, content-sized skeletons, `.trace-step`, hover-lift-one-notch.

See `/brand.md` for the full `@theme` block, the mono-crew-language law, the wordmark title-card
treatment, agentic vocabulary, and the "paper" light pairing for email/OAuth/exported PDFs.

---

## 5. Component system

### Upgrades to existing primitives (`components/ui.tsx`)
- **`Button`** — add `size="sm"`; add a pressed spring `active:scale-[0.98]`. Keep the four
  variants (the amber-fill `primary` is good).
- **`Panel`** — add optional `hover` + `selected` props (`selected` = `ring-1 ring-accent/50` +
  one ladder notch). Board cards need a selected state for select-to-scope.
- **`Tabs`** — keep horizontal `Tabs` for the **altitude toggle** (Board/Sequence/Plan). Extract a
  new vertical **`StageRail`** for the pipeline map, reusing `TabItem`'s `done/locked/live/divider`.
- **`Pill` / `StatusBadge` / `ScoreBadge`** — keep verbatim (this *is* the distinctive mono crew
  language). Extend `STATUS_COLOR` with `keyframed`, `stale`; repoint running/queued onto the cyan
  live tone.
- **`EmptyState`** — add an optional `composer` slot so an empty state can *be* a prompt box.
- **`Drawer` / `Toggle`** — keep; reuse `Drawer` for mobile inspector + mobile Director rail;
  reuse `Toggle` for the Auto-direct / Co-direct autonomy switch.
- **globals.css** — add `.stream-caret`, `.trace-step`, a `Skeleton` sizing convention, and a
  hero-only `.glow`.

### New components
| Component | What it does | Built from |
|---|---|---|
| **`CommandPalette` (⌘K)** | Keyboard-first spine (Raycast): fuzzy actions — jump to stage/shot, "render shot N", "add cast", "import source", "switch/new project". Shortcuts render as amber keycap glyphs. | focus-trapped overlay + `Input` + filtered list, ~120 lines, **no lib** |
| **`StepTrace`** | Replaces `DirectorPanel`'s flat `liveTools`/`Wrench` pills. Collapsible mono step rows (`write_script → build_storyboard → render shot 4 (best of 3) → ✓`), auto-expand running / auto-collapse done, each carrying a `shotId` to highlight the canvas. Surfaces hidden machinery: "checking continuity… picked best of 3". | the existing `tool_start`/`done` SSE events |
| **`AgentMessage`** | Extract the chat bubble from `DirectorPanel`; add **token-by-token streaming** + blinking mono caret, `@shot` reference chips, an actions footer. | existing chat thread + SSE |
| **`TimelineStrip`** | The Sequence altitude: proportional-width shot blocks, baton connector lines, drag-to-reorder, `+` to insert, render-state color, inter-block gap encodes pacing. | shot data; reorder/trim already supported |
| **`VariationGrid` / take A-B** | Surfaces best-of-N + multi-take (`finishedCount > 1` already tracked) as a pickable grid + synced A/B compare. Turns a silent backend trick into a steering affordance (addresses high script-coherence variance). | `versions` + `pickVersion` |
| **`Skeleton`** | Shimmer rectangles **sized to the final frame's aspect**, used while a shot generates instead of the bare `Spinner` in `ShotCard`. | `.shimmer` class formalized |
| **`CastChip`** | Draggable portrait-thumbnail chip (Soul-ID / Ingredients pattern) above the composer and on shots; click/drag injects the cast subject (you already anchor subjects by appearance — surface it). | `characters` + portraits |
| **`QueueDock`** | Footer status strip replacing the Queue tab: in-flight count, retryable failures, expandable. | `jobs` + `retry` |
| **`CostMeter`** | Inline pre-spend cost vs. per-project budget, shown on render buttons + batch toolbar *before* the click. | per-project budget |
| **`AutonomyToggle`** | Auto-direct (run through, review at end) vs Co-direct (pause at each gate). Maps onto existing `AWAITING_REVIEW` gates + double-gate for LONG. | `Toggle` + gate status |

---

## 6. Interaction patterns

- **Keyboard-first.** ⌘K palette; keep number-keys for stages; `J`/`K` move between shots; `R`
  render selected; `Enter` open inspector; `Esc` close. Render every shortcut as a keycap glyph.
- **Select-to-scope (single highest-value add).** Click a board card → `selected` ring **and** an
  `@shot 4` chip pins into the Director composer; the next NL instruction is scoped to it. ⌘-click
  multiple → batch chip → wired to the **existing batch ops**. Eliminates chat-only "which shot?"
  ambiguity.
- **Inline per-shot direction.** Each card gets a small ✨ "direct this shot" affordance opening an
  anchored mini-composer (per-shot direction already exists, PR9) — locality instead of routing
  every tweak through global chat.
- **Mid-generation steering.** The Director rail is persistent and SSE already streams
  `job`/`tool_start`; let the user queue an instruction while shots render and add a "stop/revise"
  affordance on in-flight `StepTrace` rows.
- **Accept/reject takes.** `VariationGrid` + A/B with explicit pick/reject per take (reuses
  `pickVersion`); rejected takes dim but aren't destroyed (matches the existing "mark stale, don't
  destroy" philosophy).
- **Reviewable fan-out.** "Make the whole thing more nighttime" → per-shot diffs proposed on the
  board (reuses `revise_service` propose-diff + the review gate), **never silent-global**.
- **Bimodal steering everywhere.** Chat for big moves; click-the-shot inline controls for precise
  tweaks; switchable anytime.

---

## 7. Onboarding & streaming / empty states

- **Born-in-chat, raised-on-canvas.** New project opens to a single centered `Composer`
  (`EmptyState` with composer slot): `"Describe the film you want to direct…"` + example chips +
  "import a long source." The instant the script/board generates, the layout springs (~200ms) into
  the three-zone board-primary shell. Run the existing **clarify Q&A (PR9)** as the "Co-direct"
  interview before first generation — a guided interview, not a blank box.
- **Streaming states (replace every bare spinner):**
  - Script / clarify output → token-by-token with a mono blinking caret (`AgentMessage`).
  - Generating shots → `Skeleton` sized to the final frame in the board cell; render-state color.
  - Director work → `StepTrace` rows resolving spinner→✓, affected card highlighting.
  - Quality machinery made visible: "checking continuity… picked best of 3" as trace chips.
- **Empty states stay instructive, not salesy** — the current `ShotBoard` empty copy ("No
  storyboard yet — the storyboard agent breaks the script into an executable shot list…") is
  already the right voice. Keep it; every empty state names the agent's job + the next action.
- **Motion discipline** — spring, 100–300ms, one state-change per animation. Grain/glow hero-only.
  Honor `prefers-reduced-motion` (already wired).

---

## 8. Build sequencing (low-risk → high-leverage)

Phased so we never bet the repo (200+ tests, 7.3k-line FE) on a big-bang rewrite. Each phase
ships standalone value.

1. **Tokens + primitives** — surface ladder + `--color-live` cyan + hairline/halos/`--glow-hero`;
   `Panel` selected/hover; `Skeleton`; shadow→ring swaps; type tracking; grain dial; spring `.rise`.
   *Pure CSS / `ui.tsx`, no logic.* Updates `brand.md`.
2. **Workspace re-shell** — `Tabs` → `StageRail` + altitude toggle + persistent Director rail +
   `QueueDock`. Reuse all existing state / SSE / poll. *The structural heart.*
3. **`StepTrace` + `AgentMessage`** — streaming + agent-trace in the Director rail (data already on
   the SSE stream); card-highlight on step resolve.
4. **Select-to-scope + `CastChip`** — the agentic feel; wire ⌘-click multi-select to batch ops.
5. **`TimelineStrip` (Sequence view) + `VariationGrid`/A-B** — continuity + variance craft
   (extrovid's actual differentiator).
6. **`CommandPalette` + `CostMeter` + `AutonomyToggle`** — polish + power-user.
7. **Dashboard / landing composer-first** rework.

### File map (what each phase touches)
- `frontend/app/globals.css` — tokens, motion primitives (P1)
- `frontend/components/ui.tsx` — primitives, `StageRail`, `Skeleton` (P1–P2)
- `frontend/components/Workspace.tsx` — three-zone re-shell (P2)
- `frontend/components/workspace/DirectorPanel.tsx` — persistent rail, `StepTrace`, `AgentMessage` (P2–P3)
- `frontend/components/workspace/ShotBoard.tsx` — `selected` state, select-to-scope, inline direct (P2,P4)
- `frontend/components/workspace/ShotInspector.tsx` — accordion split of the 997-line monolith (P2)
- `frontend/components/workspace/QueuePanel.tsx` → `QueueDock` (P2)
- new: `CommandPalette.tsx`, `TimelineStrip.tsx`, `VariationGrid.tsx`, `CastChip.tsx`, `Composer.tsx`,
  `CostMeter.tsx`, `AutonomyToggle.tsx`
- `frontend/components/Sidebar.tsx` — recede + cross-project HUD + ⌘K entry (P1/P6)
- `frontend/app/page.tsx` — composer-first dashboard + intent tiles (P7)
- `frontend/components/Landing.tsx` — title-card hero (P7)

---

## 9. Out of scope / explicitly avoid (all research-backed)
- **No anime-coded avatars / mascots.** Crew personality lives in *copy* ("the cut picked the best
  of 3 takes"), not seven cute cutscenes (oiioii's gimmick risk).
- **No invite-wall / waitlist theatrics.** extrovid is open Google-OAuth multi-user with a public
  gallery; scarcity would undercut that.
- **No full multi-track NLE.** extrovid's unit is a shot/scene, not a frame. The Sequence view is a
  low-density proportional read, **not** a 30-track timeline.
- **Don't let the Director chat become the only navigation.** The board stays the clickable map.
- **Don't hide cost** until after generation. **Don't apply wide transforms silently** — always
  diff per-shot. **Don't keep the inspector as one always-expanded wall** — accordion it.
- **No second *brand* color.** The cyan is a *machine-state* tone only, strictly subordinate to
  amber; it never appears as a CTA or brand mark.
- **Stay dark-only in the app.** The "paper" light pairing is for documents/email only.

---

## 10. Definition of done (per phase)
- **P1:** every surface uses the ladder (zero `shadow-*` on dark); running/streaming states read
  cyan; `brand.md` updated; `prefers-reduced-motion` still honored; 200+ tests green.
- **P2:** workspace is a three-zone room; the board is the default hero; the Director rail is
  persistent; Queue is a footer dock; stage map navigates; no functional regressions vs. the tab UI.
- **P3:** no bare spinner remains for AI work; Director shows a live step trace that highlights the
  affected card; script/clarify output streams token-by-token.
- **P4:** clicking a shot scopes the Director input; ⌘-click batch-steers; cast is a draggable chip.
- **P5:** Board↔Sequence toggle works on the same data; baton links render; best-of-N takes are a
  pickable A/B grid.
- **P6:** ⌘K jumps/acts across the app; render buttons show cost vs. budget before spend; autonomy
  toggle gates the pipeline.
- **P7:** a new project opens into a composer; intent tiles set length tier + HITL; landing leads
  with the title-card hero.

---

## Appendix — current-state grounding (so "keep/change" claims are accurate)
- `Workspace.tsx` (831 lines): header + sticky horizontal `Tabs` [Plan, Look, Cast, Review,
  Storyboard, Cut, Queue, Director] + docked `ShotInspector` (3rd pane desktop / `Drawer` mobile);
  dual SSE (`/projects/{id}/events`) + 5s poll on the `generating` set; number-keys 1–8 jump tabs.
- `DirectorPanel.tsx` (213): chat thread (`directorTurns`), SSE `/director/stream` →
  `tool_start` pills (`Wrench`) → `done` event with `reply` + `actions` + `state` (ProjectState
  pills: shots / rendered / stale / in-flight); suggestion chips.
- `ShotBoard.tsx` (373): scene-banded horizontal filmstrips; batch toolbar (Keyframes / Render all
  / Render chained); crew-dashboard mono counts (keyframed / rendered / running / revise); Cast
  row; `ShotCard` (thumb + `#order·model` / duration / score / stale / KF / N-takes badges) +
  `StageStrip` (kf → render → review).
- `ui.tsx` (337): `Button`, `Input`, `Panel`, `Alert`, `Eyebrow`, `Pill`, `StatusBadge`,
  `ScoreBadge`, `Toggle`, `Tabs` (+`TabItem`), `EmptyState`, `Drawer`, `cn`.
- `globals.css` (130): `@theme` warm near-black + amber tokens; `.atmosphere` grain+vignette;
  `.rise`/`.shimmer`/`.pulse-dot`/`.drawer-in`; `prefers-reduced-motion` global override.
