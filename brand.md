# Brand — extrovid

_Status: evolved 2026-06-21 — sharpened for the 2026 AI-native bar (no rebrand). Supersedes the
2026-06-10 baseline. Companion: `docs/frontend-redesign-board-room.md`._

extrovid is an AI-native director/editor: a video creation tool centered on script, previsual
development, storyboard, character consistency, and natural-language revision. The interface is a
**director's studio at golden hour** — dark, cinematic, calm, precise.

## Essence — what we protect

The rarest, most expensive half of a premium identity is already ours and almost nobody in
AI-video has it. **Protect these ferociously; changing them is the rebrand we are not doing:**

- **Warm near-black ground** (`#0c0a09`). The whole category is cool charcoal; Linear's 2025
  refresh moved *toward* warmer gray, which validates the amber bias.
- **Instrument Serif display, lowercase, italic-accent wordmark** — `extro`*`vid`*. A serif as
  display in an AI tool reads as taste. The single most unfakeable asset.
- **Mono-as-crew-language** — JetBrains Mono restricted to machine-true metadata. A *law*, not a
  habit (see Typography).
- **Film-set voice** — brief → script → look → cast → storyboard → rough cut → print it.
- **Accessibility baked in** — focus-visible rings, `prefers-reduced-motion`, `aria`, live regions.

The 2026 evolution is **execution discipline, not identity**: surface-ladder depth, a cool
machine-state tone, AI-native streaming/agent-trace language, and spring motion.

## Palette (defined in `frontend/app/globals.css` `@theme`)

Two color jobs, strictly separated: **amber = human intent**, **slate-cyan = machine working**.
This is a tungsten-vs-daylight color-temperature story — authentically filmic. Do **not** add a
second *brand* color; the cyan is a machine-state tone only and is always subordinate to amber.

```css
@theme {
  /* ── surface ladder (warm near-black, one lightness notch apart) ── */
  --color-bg:        #0c0a09;  /* canvas */
  --color-bg-soft:   #14110d;  /* sunken — inputs, wells */
  --color-panel:     #1a1611;  /* surface — cards, panels */
  --color-panel-hi:  #221d16;  /* elevated / hover */
  --color-elevated:  #2a2319;  /* NEW — popovers, dragged shot, active take (4th notch) */

  /* ── borders → prefer hairline + shadow-as-border over hard warm borders ── */
  --color-border:    #2c261d;  /* keep, use sparingly */
  --color-border-hi: #3d3527;  /* focus / active edges */
  --color-hairline:  rgba(244,239,230,0.07);  /* NEW — card separation instead of hard borders */

  /* ── text ── */
  --color-fg:    #f4efe6;  /* primary — warm off-white */
  --color-muted: #a59c8c;  /* secondary */
  --color-faint: #8a8170;  /* tertiary / metadata (was #928975 — slightly dimmer so mono recedes) */

  /* ── ONE accent = human intent (unchanged hue) ── */
  --color-accent:      #e2a44f;  /* golden-hour amber — actions, focus, selected, wordmark */
  --color-accent-soft: #b9823a;
  --color-accent-glow: rgba(226,164,79,0.16);  /* NEW — ~15% halo */

  /* ── machine-state cool tone (NEW) — render / stream / agent-working ── */
  --color-live:      #6fb3c4;  /* desaturated slate-cyan — "the crew is working" */
  --color-live-soft: #4d8595;
  --color-live-glow: rgba(111,179,196,0.14);

  /* ── semantics ── */
  --color-ok:   #79c08c;  /* success */
  --color-run:  #6fb3c4;  /* running / in-progress — REPOINTED amber → live cyan */
  --color-fail: #df6f5e;  /* errors / destructive */

  /* ── hero-only atmosphere ── */
  --glow-hero: radial-gradient(120% 80% at 50% -10%, #221a10 0%, transparent 55%);

  --radius:    0.625rem;
  --radius-sm: 0.375rem;  /* NEW — chips, keycaps, mono pills */
}
```

Dark-only product. Never hardcode hex in components — use the Tailwind tokens (`bg-panel`,
`text-muted`, `border-hairline`, `text-accent`, `text-live`, …).

## Elevation & depth

The #1 thing that dates a dark UI is depth built from borders. The 2026 tell is a **lightness
ladder**.

- Depth = the surface ladder (`bg → bg-soft → panel → panel-hi → elevated`) + hairline, **never a
  drop shadow on dark** (shadows go muddy and read 2021).
- When a ring is needed, use **shadow-as-border**: `box-shadow: 0 0 0 1px rgba(0,0,0,.5)` + a faint
  inner top-light, not a hard warm 1px border.
- **Hover lifts exactly one ladder notch** (`hover:bg-panel-hi`); no shadow bloom.
- Selected = `ring-1 ring-accent/50` + one notch.

## Typography

- **Display** (`--font-display`, Instrument Serif): page titles, project names, hero/empty-state
  title cards. Lowercase, with the brand-italic accent word: `extro`*`vid`*. **Tighten tracking to
  `-0.02em`** for an engineered, premium feel (cheapest perceived-quality win).
- **Sans** (`--font-sans`, Hanken Grotesk): body and UI copy. Body `letter-spacing: 0` (drop the
  old `0.01em` loosening).
- **Mono** (`--font-mono`, JetBrains Mono): the **crew language**. Anything machine-true is mono;
  sans never shows a machine-true number; mono never shows prose. This rule is the distinctiveness.

  | Mono is for (and only for) |
  |---|
  | durations · timecodes · shot/scene numbers · model names · seeds · costs/credits · statuses · dimensions · percentages · queue positions |

  **New mono uses:** agent-trace step rows, and ⌘K keycap glyphs — the crew narrating in the crew
  language.
- `.eyebrow`: mono, uppercase, letter-spaced section labels (and the lightweight "who's speaking"
  crew attribution, e.g. `CONTINUITY`).

## Texture & motion

- **Film grain + vignette** atmosphere (`.atmosphere`) — keep, it's a differentiator — but **dial
  and scope it**: wrapper grain `~0.025` (was `0.035`), vignette `#00000066` (was `#00000080`), and
  **off** the dense working surfaces (storyboard grid, cast list, inspector) where it fights
  legibility. Concentrate grain/glow on the shell, landing, empty-state composer, and
  render-complete moments.
- **Motion → spring, fast, earned.** Spring physics (settles, not snaps), 100–300ms, one
  state-change per animation. `.rise` retuned to `~0.38s`. Constant/slow (>400ms) ambient motion
  reads amateur.
- **AI-native motion primitives (the big modernity unlock):**
  - `.stream-caret` — blinking caret for token-by-token output (amber = intent / cyan = machine).
  - **Skeletons sized to final content** — shimmer matched to the shot frame's aspect, not generic
    bars. Never a bare spinner for AI work.
  - `.trace-step` — agent tool-event row: mono label, **cyan in-progress dot → resolves to ok/amber
    check**; auto-expand while running, auto-collapse on done.
  - **Hover = lift one ladder notch.**
- `.shimmer` for skeletons; `.pulse-dot` (cyan) for live/processing.
- All motion honors `prefers-reduced-motion` (global override in `globals.css`).

## Generation & agent states

For an AI-native product this is core texture, not a detail.

- **Streaming text** = token-by-token reveal + caret (amber for human-facing replies, cyan for
  machine narration).
- **Tool-event trace** = mono `.trace-step` rows, cyan running dot → ok/amber check; auto-collapse
  when done; each row can highlight the affected shot on the board.
- **Hidden machinery made visible** — surface best-of-N and continuity review as trace chips:
  "checking continuity… picked best of 3."
- **Live / queue** = cyan `pulse-dot`; **never a bare spinner**.
- **Pre-spend cost** shown in mono against the per-project budget *before* generating.

## Logo / wordmark

- **Primary:** serif `extro`*`vid`*, lowercase, tight negative tracking, italic `vid` in amber.
- **Title-card treatment** for hero / empty-state: large, like a *now-showing* moment, optionally
  with a single hairline rule beneath like a film slate.
- **Chrome lockup:** serif wordmark + a tiny mono build-tag beneath (e.g. a project's mono status)
  — the lockup itself demonstrates the serif+mono duality.
- **Optional square mark** (favicon/app-icon only): a minimal 1px-weight geometric aperture/slate
  glyph in amber. Never a literal camera.
- **Never:** gradient fill, glow, or bevel on the wordmark; glow on the wordmark in working chrome.
  Keep it flat serif + one italic amber word.

## Voice

Calm, specific, film-set vocabulary: *brief, script, look development, storyboard, shot, take,
dailies, cast, rough cut, print it*. Sentence case. Short. Never marketing-speak. Errors say what
happened and what to do next.

- **Crew metaphor lives in copy, not mascots.** Attribute work to the role: "the script is
  asking…", "cast locked 3 subjects", "the cut picked the best of 3 takes." Personality in the
  verb, not an avatar.
- **Agentic verbs** (mono-status friendly): `directing`, `casting`, `boarding`, `rendering`,
  `printing`, `picking best of N`, `holding for review`, `awaiting your note`.
- **Empty-state composer line:** *"Describe the video you want to direct."* + 2–3 example brief
  chips + a secondary *"or import a long source."* Generation-first, configuration-deferred.
- **Render-complete payoff:** *"Print it."* / *"That's a take."*

## Light / print context

The **app is dark-only and stays dark-only** — correct for a grading-suite tool. But two real
surfaces need a defined light pairing — **a "light mode for documents," not an app theme**:

- **Email / OAuth / transactional, and exported PDFs** (storyboards, shot lists, call sheets):
  ground `#faf7f1`, ink `#1a1611`, accent `#b9823a` (the *soft* amber — bright amber is illegible
  on white), border `#e7e0d4`. Serif for titles, **mono for all machine-true metadata** so an
  exported shot list still speaks crew-language on paper.
- **OG / social cards:** the dark title-card lockup on `#0c0a09` with the amber italic `vid` — the
  most ownable image.

## Implementation notes

- Tokens live in `frontend/app/globals.css` `@theme`; use Tailwind tokens, never raw hex.
- `frontend/AGENTS.md`: this Next.js (16) has breaking changes — read
  `node_modules/next/dist/docs/` before writing Next code.
- Rollout is phased in `docs/frontend-redesign-board-room.md` (Phase 1 = this token/primitive pass).
