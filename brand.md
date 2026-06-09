# Brand — extrovid

_Status: documented (existing design system, codified 2026-06-10)_

extrovid is an AI-native director/editor: a video creation tool centered on script,
previsual development, storyboard, character consistency, and natural-language revision.
The interface is a **director's studio at golden hour** — dark, cinematic, calm, precise.

## Palette (defined in `frontend/app/globals.css` `@theme`)

| Token | Value | Use |
|---|---|---|
| `--color-bg` | `#0c0a09` | App background (near-black, warm) |
| `--color-bg-soft` | `#14110d` | Inputs, sunken surfaces |
| `--color-panel` | `#1a1611` | Cards / panels |
| `--color-panel-hi` | `#221d16` | Hover / raised panels |
| `--color-border` | `#2c261d` | Default borders |
| `--color-border-hi` | `#3d3527` | Emphasized borders |
| `--color-fg` | `#f4efe6` | Primary text (warm off-white) |
| `--color-muted` | `#a59c8c` | Secondary text |
| `--color-faint` | `#928975` | Tertiary text / metadata |
| `--color-accent` | `#e2a44f` | Golden-hour amber — actions, highlights |
| `--color-ok` | `#79c08c` | Success |
| `--color-run` | `#e2a44f` | Running / in-progress |
| `--color-fail` | `#df6f5e` | Errors / destructive |

Dark-only product. Never hardcode hex values in components — use the Tailwind tokens
(`bg-panel`, `text-muted`, `border-border`, `text-accent`, …).

## Typography

- **Display** (`--font-display`, serif): page titles, project names. Lowercase, with the
  brand-italic accent word: `extro<span class="italic text-accent">vid</span>`.
- **Sans** (`--font-sans`): body and UI copy.
- **Mono** (`--font-mono`): production metadata — durations, model names, shot numbers,
  statuses, costs. Mono is the "crew language" of the app; anything machine-true is mono.
- `.eyebrow`: mono, uppercase, letter-spaced section labels.

## Texture & motion

- Film grain + vignette atmosphere on the app wrapper (`.atmosphere`).
- `.rise` entrance (subtle translate-up fade, stagger with `animationDelay`).
- `.shimmer` for skeletons; `.pulse-dot` for live statuses.
- All motion honors `prefers-reduced-motion` (global override in globals.css).

## Voice

Calm, specific, film-set vocabulary: *brief, script, look development, storyboard, shot,
take, dailies, cast, rough cut, print it*. Sentence case. Short. Never marketing-speak.
Errors say what happened and what to do next.
