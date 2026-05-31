# AI-native Director/Editor Product Spec v2

## Product Overview

This product is not a traditional NLE (non-linear editor) with AI features layered on top. It is an **intent-driven** video creation system built around brief, script, previsual development, storyboard, character memory, and revision workflows, with models handling generation, continuation, reference consistency, and video editing.[cite:96][cite:56]

The goal is to shift video production from a "import footage, then manually edit" workflow to a "define creative intent first, then let AI execute and iterate" workflow. This aligns with Wan2.7's positioning of moving creators from executors to directors.[cite:56][cite:110]

Version 2 of the spec adds a dedicated **Previsual Development** layer powered by Qwen LLM + Qwen image generation/editing so early concepting becomes a first-class product capability instead of an informal prompt step.[cite:96][cite:167][cite:169][cite:129]

## Product Positioning

### Positioning Statement

AI-native director/editor: a video creation tool centered on script, previsual development, storyboard, character consistency, and natural-language revision.

### What It Is Not

- It should **not** position itself as an "AI version of Adobe Premiere." The traditional timeline is not the product entry point; it is a downstream refinement surface.[cite:96][cite:151]
- In Phase 1, it should **not** aim for full multi-track post-production, complex keyframing, professional color grading, or After Effects-level compositing, because those features dilute the value of the AI-native workflow.[cite:96][cite:56]
- In Phase 1, it should **not** include multi-user collaboration; the first release should remain single-user to reduce workflow and state-management complexity while the core creation loop is still being validated.[cite:96]

### Initial Target Users

- Brand and marketing teams producing ads, product videos, and campaign assets.[cite:110]
- Social content studios producing high-volume short-form videos with heavy revision needs.[cite:115]
- AI-native narrative creators making short dramas or story-driven content that require character consistency and multi-shot continuity.[cite:56][cite:160]

## Core Value Proposition

| Dimension | Traditional video editing app | This product |
|---|---|---|
| Starting point | Starts from footage and timeline.[cite:151] | Starts from brief, script, previsual development, and storyboard.[cite:96][cite:167][cite:169] |
| Primary work unit | Clip, track, transition, effect.[cite:151] | Scene, shot, character memory, style pack, look frame, shot version.[cite:96][cite:169] |
| Editing mode | Manual trimming, dragging, effect stacking.[cite:151] | Natural-language planning and shot revision with persistent version lineage.[cite:115][cite:56] |
| Visual concepting | Usually externalized into slide decks, moodboards, or manual references.[cite:153] | Built-in visual development loop using Qwen LLM + Qwen image generation/editing.[cite:167][cite:169][cite:129] |
| Consistency management | Mostly manual asset management and post-production skill.[cite:153] | Built-in reference, continuation, and video-edit workflows.[cite:56][cite:160] |
| User role | Editor | Director / orchestrator / editor hybrid.[cite:56] |

## Problem Definition

The biggest problem with current AI video tools is not generation itself. The real problems are controllable revision, unstable characters, inconsistent multi-shot outputs, and the need to keep regenerating from scratch when results are not good enough.[cite:115][cite:56]

Traditional video editors have the opposite strength profile: they are strong at precise post-production, but they assume footage already exists. They do not natively support script planning, storyboard generation, character memory, or shot-level AI revision loops.[cite:151][cite:153]

A second gap exists even before video generation: concepting is usually fragmented across notes, Figma boards, slide decks, and ad-hoc image tools, which makes it hard to convert visual intent into reusable production controls.[cite:96][cite:169][cite:129]

The core product problem, therefore, is: how can creative intent be structured so users can continuously generate, revise, replace, and assemble video at the shot level, instead of being forced into a timeline-first workflow before the content even exists?[cite:96][cite:56]

## Product Principles

1. Script-first, not timeline-first.[cite:96][cite:56]
2. Previsual development is a product layer, not an optional side task.[cite:167][cite:169][cite:129]
3. Shot is the smallest video creation unit, but **look frame** is the smallest concepting unit.[cite:96][cite:169]
4. Every shot must have version history and acceptance criteria.[cite:96]
5. AI should plan and propose candidates first; humans should select and refine.[cite:96][cite:164]
6. References, characters, style settings, and approved concept images should live in reusable project memory, not be buried in prompts.[cite:96][cite:160][cite:169]

## Core Workflow

### Main Flow

1. The user enters a brief: product, story, platform, duration, style, audience.
2. Qwen generates a script outline, scene beats, visual direction, shot list, and prompt drafts.[cite:134][cite:164]
3. Qwen image generation and editing are used to create moodboards, character looks, environment concepts, title explorations, keyframes, and storyboard cards.[cite:167][cite:169][cite:129]
4. The user reviews and edits shots in a storyboard board, while promoting selected images into reusable references.[cite:96][cite:169]
5. The orchestrator decides which Wan2.7 model and input mode to use for each shot.[cite:56]
6. The system generates draft shot versions.
7. The user revises through natural language, with further generation, continuation, referencing, or editing when needed.[cite:115][cite:56]
8. Selected shot versions are assembled into a rough cut.
9. The user trims, reorders, captions, and exports.

### Key Interactions

- Generate this shot
- Continue from previous shot
- Match character/style
- Revise this shot
- Compare versions
- Promote concept image to style pack
- Promote concept image to character reference
- Promote concept image to first frame
- Promote concept image to storyboard card
- Replace clip in rough cut

## Previsual Development Layer

### Purpose

The previsual layer exists to bridge the gap between script intent and video generation. It turns abstract creative direction into reusable visual control assets before Wan2.7 is asked to generate shots.[cite:96][cite:167][cite:169]

### What It Produces

- Moodboards
- Style frames
- Character look explorations
- Environment concept frames
- Prop/product composition studies
- Title and on-image text explorations
- Annotated storyboard cards
- First-frame candidates for `wan2.7-i2v`
- Character / object references for `wan2.7-r2v`

### Why Qwen Image Fits This Layer

Qwen-Image is designed for strong image generation and editing, with standout performance in complex text rendering and wide stylistic coverage, which makes it suitable for posters, title cards, infographics, visual notes, and production concept frames.[cite:169][cite:182][cite:167]

Qwen-Image-Edit adds both semantic editing and appearance editing, allowing creators to keep a subject semantically consistent while changing backgrounds, wardrobe, objects, composition, or text. It also supports precise bilingual text editing while preserving original typography, which is especially useful for labeled storyboard cards and branded concept frames.[cite:129][cite:171]

### Product Capabilities in This Layer

- Generate 4-up or 8-up concept sets from a visual brief.
- Explore multiple looks for a single scene or character.
- Iteratively refine approved frames with Qwen-Image-Edit instead of restarting concept work from scratch.[cite:129][cite:171]
- Convert approved frames into production memory objects used later by Wan2.7.[cite:96][cite:160]
- Add text overlays, labels, or graphic annotations directly inside concept frames using Qwen image text-rendering / text-editing strengths.[cite:169][cite:129]

## Qwen and Wan2.7 Responsibilities

### Qwen LLM's Role

Qwen should act as the planning and orchestration layer rather than the final rendering engine. Qwen-Agent supports assistants, function calling, MCP, and multi-tool workflows, which makes it well-suited for planner / router / reviewer responsibilities inside the product.[cite:134][cite:138][cite:162][cite:164]

Qwen LLM is responsible for:

- Brief parsing: convert user intent into structured creative requirements.[cite:134]
- Script generation: generate script structure and scene beats.[cite:134]
- Visual brief generation: generate style directions, character notes, mood references, and shot intent for the image layer.[cite:96][cite:167]
- Storyboard planning: break work into shots, durations, camera, emotion, action, and transitions.
- Routing: decide which Wan model should handle each shot.
- Review: evaluate outputs against acceptance rules and propose revisions.
- Memory orchestration: carry character cards, style packs, look frames, references, and prior versions into the next generation cycle.[cite:96]

### Qwen Image / Qwen-Image-Edit Role

Qwen image models should power the previsual stage before video generation begins.[cite:167][cite:169][cite:129]

| Model layer | Product role | Main use |
|---|---|---|
| Qwen-Image | Concept-generation engine | Generate moodboards, style frames, title explorations, visual boards, environment looks, and first-pass concept imagery.[cite:167][cite:169][cite:182] |
| Qwen-Image-Edit | Concept-refinement engine | Perform iterative semantic and appearance edits, preserving visual intent while refining character look, composition, objects, or typography.[cite:129][cite:171] |

### Wan2.7's Role

Wan2.7 is positioned as a four-model video suite that covers generation, continuation, reference-driven workflows, and editing.[cite:56][cite:142]

| Model | Product role | Main use |
|---|---|---|
| `wan2.7-t2v` | Draft-generation engine | Generate shot drafts directly from a brief or script.[cite:56] |
| `wan2.7-i2v` | Controlled-generation engine | First-frame generation, first/last-frame control, continuation, and guided motion flow.[cite:56][cite:159][cite:163] |
| `wan2.7-r2v` | Consistency engine | Character, object, style, voice, and cross-shot consistency.[cite:56][cite:160][cite:163] |
| `wan2.7-videoedit` | Revision engine | Natural-language editing of existing shots: scene, wardrobe, weather, action, camera, dialogue, and more.[cite:56][cite:110][cite:115] |

## Data Model

### Core Entities

- `Project`
- `Brief`
- `CharacterProfile`
- `StylePack`
- `ReferenceAsset`
- `VisualConceptSet`
- `LookFrame`
- `MoodboardAsset`
- `StoryboardCardAsset`
- `Scene`
- `Shot`
- `ShotVersion`
- `GenerationJob`
- `TimelineSequence`
- `RevisionRequest`

### Data Model Principles

- `ShotVersion` is the most important execution entity. Every generate, continue, or edit operation creates a new version instead of overwriting an old output.[cite:96]
- `LookFrame` is the most important previsual entity. It represents an approved concept image that can be promoted into downstream production memory.[cite:96][cite:169]
- `CharacterProfile` stores identity constraints such as facial attributes, hairstyle, wardrobe rules, voice traits, and forbidden changes.[cite:160]
- `StylePack` encapsulates style, lighting, camera language, palette, and brand rules so those do not need to be rewritten in every shot prompt.[cite:96]
- `VisualConceptSet` groups a batch of exploration frames generated from a single visual brief, enabling side-by-side concept selection.[cite:96]
- `GenerationJob` must be independent because Wan-style workflows are asynchronous and require result polling / ingestion.[cite:56]

### Suggested Fields (Condensed)

```ts
Project {
  id, title, ownerId, status, aspectRatio, targetDurationSec
}

CharacterProfile {
  id, projectId, name, description, faceLock, voiceLock, wardrobeRules, forbiddenChanges, referenceLookFrameIds
}

StylePack {
  id, projectId, label, visualStyle, lighting, cameraLanguage, palette, negativeRules, lookFrameIds
}

VisualConceptSet {
  id, projectId, sceneId, brief, type, status, candidateLookFrameIds, selectedLookFrameIds
}

LookFrame {
  id, projectId, conceptSetId, prompt, sourceModel, imageAssetId, tags, promotedAs, selected
}

Shot {
  id, sceneId, order, purpose, durationSec, beat, cameraSpec, performanceSpec, preferredModel, acceptanceRules, referenceLookFrameIds
}

ShotVersion {
  id, shotId, parentVersionId, model, prompt, inputAssets, outputAssetId, status, score, selected
}

GenerationJob {
  id, shotVersionId, provider, model, taskId, status, startedAt, completedAt, failureReason
}
```

## Information Architecture and Screens

### Main Workspaces

1. **Brief Studio**: enter project goals, duration, platform, brand constraints, and character setup.
2. **Script Editor**: edit script and scene beats.
3. **Look Development Board**: generate and compare concept images, style frames, character looks, and moodboards using Qwen image models.[cite:167][cite:169][cite:129]
4. **Storyboard Board**: card or list view of shots, with per-shot generation and revision.
5. **Shot Inspector**: inspect prompt, acceptance rules, references, and version history.
6. **Reference Memory**: manage character cards, style packs, look frames, reference images, reference clips, and voice settings.
7. **Generation Queue**: track job progress, failures, retries, and cost signals.
8. **Rough Cut Timeline**: only the minimal trim / reorder / caption / export surface.

### Phase 1 UI Principles

- The entry point should go directly to `Project > Brief > Script > Look Development > Storyboard`, not to a blank timeline.[cite:96]
- The timeline should be a downstream assembly surface, not the creation entry point.[cite:151][cite:96]
- Every concept set should show prompt, tags, selected frames, and promotion actions.
- Every shot card should clearly show purpose, duration, model, version count, state, and references.
- Version compare must support A/B preview and one-click selection.
- Phase 1 should **not** include multiplayer collaboration; keep permissions simple with a single project owner until the workflow is stable.[cite:96]

## Agent Architecture

### Recommended Agent / Tool Breakdown

1. `BriefAgent`: parse user input and fill missing fields.
2. `ScriptAgent`: generate script outline and scene beats.
3. `VisualDevelopmentAgent`: generate visual briefs and concept prompts for Qwen image models.[cite:96][cite:167]
4. `ImageConceptTool`: generate concept sets through Qwen-Image.
5. `ImageRefineTool`: iteratively edit concept frames through Qwen-Image-Edit.[cite:129][cite:171]
6. `StoryboardAgent`: generate shot list and storyboard JSON.
7. `RoutingAgent`: choose `t2v` / `i2v` / `r2v` / `videoedit` for each shot.[cite:56]
8. `ExecutionTool`: submit jobs, poll status, ingest outputs.
9. `ReviewAgent`: validate output against acceptance rules and generate revision suggestions.
10. `RoughCutAgent`: build a rough cut from selected shot versions.

### Function Calling Interface Example

```ts
type GenerateScript = (brief: BriefInput) => ScriptDraft;
type GenerateVisualBrief = (script: ScriptDraft, scene: SceneDraft) => VisualBrief;
type GenerateConceptSet = (visualBrief: VisualBrief) => VisualConceptSet;
type RefineLookFrame = (lookFrameId: string, instruction: string) => LookFrame;
type GenerateStoryboard = (script: ScriptDraft, selectedLookFrames: LookFrame[]) => Storyboard;
type PlanWanJob = (shot: Shot, context: PlannerContext) => WanJob;
type SubmitWanJob = (job: WanJob) => { taskId: string };
type PollWanJob = (taskId: string) => JobStatus;
type ReviewShotVersion = (shot: Shot, version: ShotVersion) => ReviewResult;
type BuildRoughCut = (versions: ShotVersion[]) => TimelineSequence;
```

## Phase Plan

## Phase 0: Design and Technical Validation

### Goal

- Define storyboard schema, visual concept schema, data model, and task flow.
- Validate that the Qwen planning layer can connect cleanly with the Qwen image layer and Wan execution layer.
- Build the minimum concept-to-shot generation loop.

### Scope

- Brief -> Script -> Visual Brief -> Concept Set -> Storyboard JSON pipeline.
- Basic project / concept / shot / version schema.
- Single-shot job submission, polling, and output ingestion.
- Basic preview UI.

### Not Included

- No timeline.
- No collaboration.
- No full character memory UI.

### Exit Criteria

- A brief can be converted into a visual concept set and an executable shot list.
- A selected concept image can be promoted into a shot reference and used to generate a shot.

## Phase 1: MVP (Single-User AI-native Director/Editor)

### Product Goal

Build the first testable single-user product that validates whether a brief-first + script-first + look-dev-first + shot-first + version-first workflow is materially better than a traditional timeline-first workflow for this use case.[cite:96][cite:151]

### Core Features

- Project / Brief creation
- Script Editor
- Look Development Board
- Storyboard Board
- Shot-level generation and per-shot actions
- `wan2.7-t2v` for drafting
- `wan2.7-i2v` for first-frame, first/last-frame, and continuation control.[cite:159][cite:163]
- Qwen-Image concept generation
- Qwen-Image-Edit concept refinement
- Promotion of concept images into `StylePack`, `CharacterProfile`, first-frame candidates, and storyboard references.[cite:169][cite:129][cite:171]
- Version history and A/B compare
- Rough cut timeline (trim / reorder / basic caption / export)
- Queue / status / retry

### Qwen Usage

- Auto-generate script and scene beats.[cite:134][cite:164]
- Auto-generate visual briefs and concept prompts for look development.[cite:96][cite:167]
- Auto-generate shot breakdown and prompt drafts.
- Auto-generate acceptance rules and negative constraints.
- Suggest revisions when outputs fail or are weak.

### Wan2.7 Usage

- `t2v`: generate first-shot drafts from script or prompt.[cite:56]
- `i2v`: perform first-frame control, first/last-frame control, and continuation using approved concept images as references when relevant.[cite:56][cite:159][cite:163]

### Explicitly Not Included

- No multiplayer collaboration.
- No full `r2v` character-consistency workspace.
- No full natural-language revision workflow through `videoedit`.
- No advanced audio mixing.
- No full professional multi-track NLE.

### Success Metrics

- A user can go from brief to rough-cut export in one session.
- A 15 to 30 second video can be assembled from 5 to 10 shots and exported successfully.
- Users can generate visual concepts before video generation without leaving the product.[cite:96][cite:169]
- Most user time is spent selecting concepts, selecting versions, and issuing revisions, not manually managing assets.

## Phase 2: Character Consistency and Director Controls

### Product Goal

Upgrade the product from "can generate" to "can stay consistent" across multi-shot sequences, multiple subjects, and reusable style systems.[cite:56][cite:160]

### Core Features

- Character Profile UI
- Style Pack UI
- Reference Memory panel
- Cross-shot reference inheritance
- `wan2.7-r2v` integration
- Multi-shot consistency checking
- Voice / subject reference settings
- Style pack generation from approved look frames
- Character profile initialization from concept art

### Qwen Usage

- Auto-inject project memory into prompts.
- Apply character and brand constraints per shot.
- Detect continuity violations across shots.
- Suggest which look frames should become persistent references.

### Wan2.7 Usage

- `r2v`: character, object, style, voice, and cross-shot consistency control.[cite:160][cite:163]

### Success Metrics

- Character appearance and style stability improve materially in multi-shot projects.
- Users no longer need to restate character prompts for every shot.
- Look development assets become reliable production references instead of disposable concept art.[cite:96][cite:160]

## Phase 3: True AI-native Revision Editor

### Product Goal

Build the product's most important editing capability: instead of regenerating whole shots, users can iteratively revise a shot like a director giving notes.[cite:115][cite:56]

### Core Features

- `wan2.7-videoedit` integration
- Natural-language revision panel
- Common edit templates: replace / add / remove / change scene / relight / restyle
- Dialogue rewrite + lip-sync-aware editing
- Version diff viewer
- Auto-proposed revision plans
- Bridge from Qwen-Image-Edit concept refinements to Wan video revisions when a change should move from still exploration into motion output.[cite:129][cite:171][cite:56]

### Qwen Usage

- Turn user revision requests into structured edit instructions.
- Turn review outcomes into multi-step edit plans.
- Provide fallback strategies when edits fail.
- Suggest whether a change should be explored first in still-image mode or applied directly in video mode.

### Wan2.7 Usage

- `videoedit`: edit and refine existing shots.[cite:56][cite:110][cite:115]

### Success Metrics

- Users can reach delivery-quality iterations without breaking shot lineage.
- Revision throughput and success rate outperform brute-force regeneration workflows.

## Phase 4: Commercialization and Scale

### Goal

Turn the product into a system that teams can adopt, not just a single-user creation tool.

### Candidate Features

- Collaboration
- Comment / review / approval
- Brand workspace
- Asset library / reusable templates
- Usage / cost analytics
- Role-based permissions
- Batch generation
- API / webhook / automation pipeline
- Shared concept libraries and reusable style systems

### Dependencies

- Phase 1 through Phase 3 workflows are stable.
- Shot versioning, concept memory, character memory, and revision engine behavior are predictable.

## Recommended Phase 1 Engineering Breakdown

### Frontend

- App shell
- Project dashboard
- Brief form
- Script editor
- Look development board
- Storyboard board
- Shot inspector
- Version compare modal
- Rough cut timeline
- Queue status panel

### Backend

- Auth (minimal at first)
- Project / Concept / Shot / Version CRUD
- Orchestrator service
- Qwen image adapter
- Wan job adapter
- Job queue / polling worker
- Asset ingest service
- Prompt / revision / concept log persistence

### AI Layer

- Qwen planning prompts
- Visual brief prompts
- Storyboard schema validation
- Routing rules engine
- Review / critique prompts
- Concept promotion logic

## Development Priority Order

1. Lock the storyboard schema and visual concept schema first.
2. Implement `LookFrame`, `ShotVersion`, and job lifecycle next.
3. Build the Qwen planning layer.
4. Integrate Qwen-Image and Qwen-Image-Edit.
5. Integrate `t2v` / `i2v`.
6. Build the rough cut timeline.
7. Add reference memory, `r2v`, and `videoedit` after that.

## Open Product Questions

These should be resolved before full implementation begins:

1. **Should Phase 1 be fully script-first at entry, or should footage-first projects also exist?**
2. **Should look development be scene-level, shot-level, or both?**
3. **How should version compare work?** Should AI score versions, or should selection be entirely user-driven?
4. **How ambitious should the rough cut timeline be?** Assemble-only, or assemble + transitions + music + subtitles?
5. **Should character/style memory schema be created in Phase 1 even if the richer UI ships later?**
6. **How transparent should prompts be?** Should users see the raw prompts, or only the higher-level directing language?
7. **Should generation cost and retry counts be surfaced in-product?**
8. **Should there be a director-notes panel for shot-by-shot review?**
9. **Should text-in-image capabilities be exposed explicitly for storyboard labeling and branded title exploration?** Qwen image models support strong text rendering and precise bilingual text editing, which could become a differentiating UX capability in previsual mode.[cite:169][cite:129][cite:171]

## Implementation Summary for an AI Coding Agent

### First Objective

Build a single-user web app that can turn a brief into script, visual concepts, and storyboard, execute shot-level generation, save versions, preview outputs, and assemble a rough cut. Phase 1 should not include collaboration, full character-consistency UI, full natural-language revision editing, or a professional multi-track editor.[cite:96]

### Minimum Deliverable

- Full CRUD for `Project`, `VisualConceptSet`, `LookFrame`, `Shot`, `ShotVersion`, and `GenerationJob`
- Brief -> Script -> Visual Brief -> Concept Set -> Storyboard planner pipeline
- Look Development Board
- Shot board and shot inspector
- Qwen-Image / Qwen-Image-Edit adapter
- `wan2.7-t2v` / `wan2.7-i2v` job adapter
- Queue worker + polling
- Asset ingest
- Rough cut assemble view

### Architecture Requirements

- Single-user project model
- All previsual work centered on `VisualConceptSet` and `LookFrame`
- All video generation and revision centered on `ShotVersion`
- Timeline as downstream assembly layer, not the system core
- Extension points reserved for future `r2v` and `videoedit`

## Recommended Next Decisions

The three most important immediate product decisions are:

- Should Phase 1 be fully script-first at entry?
- Should the rough cut timeline include captions and background music, or only assembly?
- Should `CharacterProfile` and `StylePack` tables be created in Phase 1 even if the richer UI is postponed to Phase 2?
