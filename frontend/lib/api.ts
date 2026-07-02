// Typed client for the extrovid backend. Browser-side; per-user Bearer token.

import { type AuthUser, clearAuth, getToken } from "@/lib/auth";

export type { AuthUser };

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "https://www.extrovid.xyz/api";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") window.dispatchEvent(new Event("extrovid-unauthorized"));
    throw new Error("Unauthorized — please sign in again.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      const d = body.detail;
      if (typeof d === "string") detail = d;
      else if (Array.isArray(d)) detail = d.map((x) => x?.msg ?? JSON.stringify(x)).join("; ");
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ───────────────────────── types ─────────────────────────

export type ProjectStats = {
  scenes: number;
  shots: number;
  rendered_shots: number;
  cuts: number;
  avg_score?: number | null; // mean AI dailies score across scored takes
};

export type Project = {
  id: string;
  title: string;
  owner_id: string;
  status: string;
  aspect_ratio: string;
  target_duration_sec: number;
  format?: string | null; // content intent (length selector)
  budget_usd?: number | null; // review-gate spend ceiling (P3)
  autonomy?: "co" | "auto"; // "co" = pause at the review gate; "auto" = run straight through
  created_at: string;
  stats?: ProjectStats | null;
};

// content intent / length preset
export type VideoFormat = "social" | "ad" | "explainer" | "youtube" | "documentary";

export type SceneBeat = { order: number; description: string; narration?: string | null; dialogue?: string | null };
export type Scene = {
  id: string;
  order: number;
  title: string;
  summary: string;
  beats: SceneBeat[];
  est_duration_sec: number;
  act_id?: string | null; // LONG tier: the chapter this scene belongs to
  stale?: boolean; // an upstream artifact changed after this was planned
  approved?: boolean; // signed off at the review gate
  locked?: boolean; // frozen against bulk regeneration
};

// LONG-tier chapter/act (the structure above scenes)
export type Act = {
  id: string;
  order: number;
  title: string;
  hook: string;
  open_loop: string;
  summary: string;
};

export type LookFrame = {
  id: string;
  prompt: string;
  tags: string[];
  promoted_as: string;
  selected: boolean;
  image_asset_id: string | null;
  image_url: string | null;
  parent_frame_id?: string | null;
  review?: Review | null; // keyframe gate verdict (set once reviewed)
  score?: number | null; // keyframe gate score 0-10
};
export type VisualBrief = {
  scene_order: number;
  visual_style: string;
  mood: string;
  palette: string[];
  lighting: string;
  camera_language: string;
  character_notes?: string | null;
  environment_notes?: string | null;
  negative_rules?: string[];
};
export type ConceptSet = {
  id: string;
  scene_order: number;
  brief: string;
  type: string;
  status: string;
  visual_brief?: VisualBrief | null;
  look_frames: LookFrame[];
};

export type CameraSpec = { shot_size: string; angle: string; movement: string; lens?: string | null };
export type PerformanceSpec = { subject: string; action: string; emotion?: string | null };
export type ShotTransition = "cut" | "dissolve" | "fade" | "match_cut" | "none";
export type Shot = {
  id: string;
  order: number;
  scene_order: number;
  purpose: string;
  duration_sec: number;
  beat: string;
  camera_spec: CameraSpec;
  performance_spec: PerformanceSpec;
  preferred_model: string;
  acceptance_rules: string[];
  transition: string;
  extra_direction: string | null;
  character_id: string | null;
  framing?: string | null; // blocking: positions + facing + focus
  screen_direction?: string | null; // 180° line: subject facing/movement direction
  dialogue?: string | null; // the one spoken line in this shot
  speaker?: string | null; // who speaks it ('narrator' for VO)
  vo_asset_id?: string | null; // synthesized voiceover audio
  camera_id?: number; // physical camera setup identity
  first_frame_desc?: string | null; // keyframe contract: planned opening snapshot
  last_frame_desc?: string | null;
  motion_desc?: string | null;
  variation_type?: string;
  keyframe_frame_id?: string | null; // generated keyframe image (i2v/r2v seed)
  last_keyframe_frame_id?: string | null; // planned closing keyframe (next shot's seed)
  render_mode?: string; // "video" = full generation; "still" = freeze-frame clip
  suggest_still?: boolean; // advisory: low-motion shot, cheap candidate for a still
  keyframe_verdict?: string | null; // keyframe gate: "pass" | "revise" | null
  keyframe_score?: number | null; // keyframe gate score 0-10
  keyframe_url?: string | null; // keyframe image — the board's pre-render poster
  stale?: boolean; // an upstream artifact changed after this was planned
  approved?: boolean; // signed off at the review gate
  locked?: boolean; // frozen against bulk regeneration
};

/** PATCH body for a shot — all fields optional, only set fields are applied. */
export type ShotUpdate = {
  purpose?: string;
  beat?: string;
  duration_sec?: number; // 0 < x <= 15
  camera_spec?: CameraSpec;
  performance_spec?: PerformanceSpec;
  transition?: ShotTransition;
  acceptance_rules?: string[];
  extra_direction?: string | null;
  character_id?: string | null;
  framing?: string | null;
  screen_direction?: string | null;
  dialogue?: string | null;
  speaker?: string | null;
  first_frame_desc?: string | null;
  last_frame_desc?: string | null;
  motion_desc?: string | null;
  render_mode?: "video" | "still";
};

export type ReviewSuggestion = { kind: "edit" | "retake"; instruction: string };
export type Review = {
  verdict: "pass" | "revise";
  score: number;
  notes: string[];
  suggestions: ReviewSuggestion[];
  continuity_notes?: string[]; // cross-shot drift vs the previous shot's frame
};

export type ShotVersion = {
  id: string;
  shot_id: string;
  parent_version_id?: string | null;
  model: string | null;
  prompt?: string | null;
  status: string;
  selected: boolean;
  output_asset_id: string | null;
  video_url: string | null;
  thumbnail_url?: string | null;
  duration_sec?: number | null;
  score?: number | null;
  review?: Review | null;
  routing_note?: string | null;
  job_id: string | null;
  job_status: string | null;
  failure_reason: string | null;
};

export type Job = {
  id: string;
  status: string;
  provider: string | null;
  model: string | null;
  started_at: string | null;
  completed_at: string | null;
  failure_reason: string | null;
  cost_usd: number;
  shot_id: string;
  shot_order: number;
  shot_purpose: string;
  version_id: string;
  thumbnail_url: string | null;
};

export type ClipSpec = { shot_version_id: string; in_sec?: number; out_sec?: number | null };

export type RoughCut = {
  id: string;
  status: string;
  output_asset_id: string | null;
  video_url: string | null;
  shot_version_ids: string[];
  clips?: ClipSpec[] | null;
  options?: { captions?: boolean; music?: boolean; voiceover?: boolean } | null;
  created_at?: string | null;
  published: boolean;
  published_id: string | null;
};

export type AuthResponse = { token: string; user: AuthUser };
export type PublicVideo = {
  id: string;
  title: string;
  aspect_ratio: string;
  published_at: string;
  stream_url: string;
};

export type Character = {
  id: string;
  name: string;
  description: string | null;
  reference_image_urls: string[];
  wardrobe_rules?: string[];
  portrait_image_urls?: Record<string, string>; // {front, side, back} turnaround
};
export type StylePack = { id: string; label: string; image_urls: string[] };

// projected spend to render the current plan once (review-gate cost preview)
export type PlanCost = {
  shots: number;
  video_usd: number;
  image_usd: number;
  tts_usd: number;
  total_usd: number;
};

export type ProjectState = {
  project_status: string | null;
  target_duration_sec: number | null;
  tier?: string | null; // short | medium | long (derived from target duration)
  gated?: boolean; // medium/long require approval before generation
  scenes_approved?: number;
  shots_approved?: number;
  projected_cost_usd?: number;
  cost_breakdown?: PlanCost;
  budget_usd?: number | null; // approved spend ceiling (None = unset)
  over_budget?: boolean; // projected cost exceeds the budget
  has_brief: boolean;
  scenes: number;
  stale_scenes: number;
  concept_sets: number;
  shots: number;
  stale_shots: number;
  shots_with_keyframe: number;
  shots_with_take: number;
  shots_with_selected_take: number;
  jobs_in_flight: number;
  failed_jobs: number;
  characters: { name: string; has_portraits: boolean; has_references: boolean }[];
  style_packs: number;
  rough_cuts: number;
};

// ── review gate (P1) ──
export type AnnotationKind = "scene" | "shot" | "visual_brief" | "plan";
export type AnnotationIntent = "comment" | "change";
export type Annotation = {
  id: string;
  target_kind: AnnotationKind;
  target_id?: string | null;
  field?: string | null;
  intent: AnnotationIntent;
  text: string;
  status: "open" | "applied" | "resolved";
  created_at: string;
};
// non-destructive revision proposal (the before/after diff for the gate)
export type ReviseProposal = {
  target: string;
  dry_run: boolean;
  kind: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  instruction: string;
};

export type DirectorAction = { tool: string; args: Record<string, unknown>; result_summary: string };
export type DirectorResponse = { reply: string; actions: DirectorAction[]; state: ProjectState };
export type DirectorTurn = { id: string; role: "user" | "assistant"; content: string; created_at: string };

// ── clarifying questions (plan stage) ──
export type ClarifyQuestion = {
  id: string;
  question: string;
  why: string;
  options: string[]; // 2-4 concrete suggestions
  allow_custom: boolean;
};
export type ClarifyResult = {
  needs_clarification: boolean;
  questions: ClarifyQuestion[]; // max 4, empty when not needed
  prompt_assessment: string; // one line: what is clear / what is missing
};
export type ClarifyAnswer = { question_id: string; question: string; answer: string };

export type BriefInput = {
  raw_prompt: string;
  product?: string | null;
  story?: string | null;
  platform: string;
  target_duration_sec: number;
  aspect_ratio: string;
  style?: string | null;
  audience?: string | null;
  format?: string | null;
};
export type ScriptDraft = {
  logline: string;
  scenes: {
    order: number;
    title: string;
    summary: string;
    beats: SceneBeat[];
    est_duration_sec: number;
  }[];
};

export type PipelineResult = {
  brief: { product?: string; target_duration_sec: number; platform: string; audience?: string };
  script: { logline: string; scenes: { order: number; title: string }[] };
  storyboard: { scenes: { scene_order: number; shots: Shot[] }[] };
  concept_specs: unknown[];
};

// ───────────────────────── endpoints ─────────────────────────

// ── auth ──
export const register = (email: string, password: string) =>
  api<AuthResponse>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
export const login = (email: string, password: string) =>
  api<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const me = () => api<AuthUser>("/auth/me");
// account preferences — advisory default format for new projects (pre-fill only)
export const updatePreferences = (default_format: string | null) =>
  api<AuthUser>("/auth/me", { method: "PATCH", body: JSON.stringify({ default_format }) });
export const rotateToken = () => api<{ token: string }>("/auth/rotate-token", { method: "POST" });
export const logout = () => api<void>("/auth/logout", { method: "POST" });
// current_password omitted for a Google-only account setting its first password
export const changePassword = (new_password: string, current_password?: string) =>
  api<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(current_password ? { current_password, new_password } : { new_password }),
  });
export const deleteAccount = () => api<void>("/auth/me", { method: "DELETE" });
export const googleLoginUrl = () => `${API_BASE}/auth/google/login`;

// ── gallery ──
export const listGallery = () => api<PublicVideo[]>("/gallery");
export const galleryVideoUrl = (publishedId: string) => `${API_BASE}/gallery/${publishedId}/video`;
export const publishCut = (id: string, seqId: string) =>
  api<PublicVideo>(`/projects/${id}/rough-cut/${seqId}/publish`, { method: "POST" });
export const unpublishCut = (id: string, seqId: string) =>
  api<void>(`/projects/${id}/rough-cut/${seqId}/publish`, { method: "DELETE" });

// ── projects ──
export const listProjects = () => api<Project[]>("/projects");
export const createProject = (
  body: { title?: string; aspect_ratio?: string; target_duration_sec?: number; format?: string } = {},
) => api<Project>("/projects", { method: "POST", body: JSON.stringify(body) });
export const getProject = (id: string) => api<Project>(`/projects/${id}`);
export const updateProject = (
  id: string,
  body: {
    title?: string;
    aspect_ratio?: string;
    target_duration_sec?: number;
    format?: string;
    autonomy?: "co" | "auto";
  },
) => api<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteProject = (id: string) => api<void>(`/projects/${id}`, { method: "DELETE" });

export const runPipeline = (id: string, raw_prompt: string, clarifications: ClarifyAnswer[] = []) =>
  api<PipelineResult>(`/projects/${id}/run`, {
    method: "POST",
    body: JSON.stringify(clarifications.length ? { raw_prompt, clarifications } : { raw_prompt }),
  });

// stateless clarify pass — director Q&A before planning; nothing is persisted
export const clarifyBrief = (id: string, raw_prompt: string) =>
  api<ClarifyResult>(`/projects/${id}/clarify`, {
    method: "POST",
    body: JSON.stringify({ raw_prompt }),
  });

// Full plan (Brief->Storyboard) is streamed over SSE — see lib/sse.ts `streamSSE` and
// PlanPanel. The endpoint emits live per-stage progress and persists atomically; a single
// blocking request can't be used (multi-minute plans get idle-cut → "Failed to fetch").
export const PLAN_STREAM_PATH = (id: string) => `/projects/${id}/plan/stream`;

export const getScript = (id: string) => api<Scene[]>(`/projects/${id}/script`);
export const getConceptSets = (id: string) => api<ConceptSet[]>(`/projects/${id}/concept-sets`);
export const getStoryboard = (id: string) => api<Shot[]>(`/projects/${id}/storyboard`);
export const updateShot = (id: string, shotId: string, patch: ShotUpdate) =>
  api<Shot>(`/projects/${id}/shots/${shotId}`, { method: "PATCH", body: JSON.stringify(patch) });

export const generateImages = (id: string, csId: string, limit?: number) =>
  api<LookFrame[]>(`/projects/${id}/concept-sets/${csId}/generate-images${limit ? `?limit=${limit}` : ""}`, {
    method: "POST",
  });
export const promoteFrame = (id: string, frameId: string, target: string, name?: string) =>
  api<{ frame_id: string; promoted_as: string }>(`/projects/${id}/look-frames/${frameId}/promote`, {
    method: "POST",
    body: JSON.stringify({ target, name }),
  });
export const refineFrame = (id: string, frameId: string, instruction: string) =>
  api<LookFrame>(`/projects/${id}/look-frames/${frameId}/refine`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });

export const generateShot = (
  id: string,
  shotId: string,
  opts?: {
    first_frame_asset_id?: string;
    reference_asset_ids?: string[];
    // parallel to reference_asset_ids: identity|outfit|prop|scene|style — what to take from each
    reference_roles?: string[];
    character_id?: string;
    continue_from_previous?: boolean;
    num_takes?: number; // best-of-N fan-out (1-4); winner auto-selected by review
  },
) =>
  api<ShotVersion>(`/projects/${id}/shots/${shotId}/generate`, {
    method: "POST",
    body: JSON.stringify(opts ?? {}),
  });

// batch rendering — keyframed shots parallelize; chained shots queue on upstream takes
export const generateScene = (id: string, sceneOrder: number, continueFromPrevious = false) =>
  api<ShotVersion[]>(`/projects/${id}/scenes/${sceneOrder}/generate-all`, {
    method: "POST",
    body: JSON.stringify({ continue_from_previous: continueFromPrevious }),
  });
export const generateAllShots = (id: string, continueFromPrevious = false) =>
  api<ShotVersion[]>(`/projects/${id}/generate-all`, {
    method: "POST",
    body: JSON.stringify({ continue_from_previous: continueFromPrevious }),
  });

// one-click Produce: portraits -> keyframes -> videos -> voiceovers -> rough cut.
// "gated" pauses after newly created keyframes so the board can be reviewed before
// video budget is spent; calling again resumes (each stage only does missing work).
export type ProduceStatus = {
  state: "idle" | "running" | "paused" | "done" | "error" | "stopped";
  stage: string | null;
  detail: string | null;
  running: boolean;
};
export const startProduce = (id: string, mode: "gated" | "auto" = "gated") =>
  api<ProduceStatus>(`/projects/${id}/produce`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
export const getProduceStatus = (id: string) => api<ProduceStatus>(`/projects/${id}/produce`);
export const stopProduce = (id: string) =>
  api<ProduceStatus>(`/projects/${id}/produce/stop`, { method: "POST" });

// keyframe-first: the shot's opening frame as a refinable image before video spend
export const generateKeyframe = (id: string, shotId: string) =>
  api<LookFrame>(`/projects/${id}/shots/${shotId}/keyframe`, { method: "POST" });
export const generateAllKeyframes = (id: string) =>
  api<LookFrame[]>(`/projects/${id}/storyboard/keyframes`, { method: "POST" });
// keyframe gate: re-run the identity/composition/view review on the shot's keyframe
export const reviewKeyframe = (id: string, shotId: string) =>
  api<LookFrame>(`/projects/${id}/shots/${shotId}/keyframe/review`, { method: "POST" });
// voiceover: synthesize the shot's spoken line (TTS) into a stored audio asset
export const generateVoiceover = (id: string, shotId: string) =>
  api<Shot>(`/projects/${id}/shots/${shotId}/voiceover`, { method: "POST" });

// cast pipeline
export const generateCast = (id: string) =>
  api<Character[]>(`/projects/${id}/cast/generate`, { method: "POST" });
export const generatePortraits = (id: string, characterId: string) =>
  api<Character>(`/projects/${id}/characters/${characterId}/portraits`, { method: "POST" });

// director runtime
export const getProjectState = (id: string) => api<ProjectState>(`/projects/${id}/state`);
export const reviseArtifact = (id: string, target: string, instruction: string) =>
  api<{ target: string; revised: Record<string, unknown> }>(`/projects/${id}/revise`, {
    method: "POST",
    body: JSON.stringify({ target, instruction }),
  });
// dry-run: a non-destructive before/after proposal; accept it with applyRevision
export const proposeRevision = (id: string, target: string, instruction: string) =>
  api<ReviseProposal>(`/projects/${id}/revise`, {
    method: "POST",
    body: JSON.stringify({ target, instruction, dry_run: true }),
  });
// commit a proposal's exact `after` (deterministic — no agent re-run)
export const applyRevision = (id: string, target: string, after: Record<string, unknown>) =>
  api<{ target: string; revised: Record<string, unknown> }>(`/projects/${id}/revise/apply`, {
    method: "POST",
    body: JSON.stringify({ target, after }),
  });

// ── review gate (P1): approve / lock / annotate the plan before generation ──
export const getPlanCost = (id: string) => api<PlanCost>(`/projects/${id}/plan/cost`);
export const approvePlan = (
  id: string,
  body?: { scene_ids?: string[]; shot_ids?: string[]; budget_usd?: number },
) =>
  api<{
    project_status: string;
    scenes_total: number;
    scenes_unapproved: number;
    approved: boolean;
    budget_usd?: number | null;
  }>(`/projects/${id}/plan/approve`, { method: "POST", body: JSON.stringify(body ?? {}) });
export const lockScene = (id: string, sceneId: string, locked: boolean) =>
  api<{ id: string; locked: boolean }>(`/projects/${id}/scenes/${sceneId}/lock`, {
    method: "POST",
    body: JSON.stringify({ locked }),
  });
export const lockShot = (id: string, shotId: string, locked: boolean) =>
  api<{ id: string; locked: boolean }>(`/projects/${id}/shots/${shotId}/lock`, {
    method: "POST",
    body: JSON.stringify({ locked }),
  });
export const createAnnotation = (
  id: string,
  body: {
    target_kind: AnnotationKind;
    target_id?: string | null;
    field?: string | null;
    intent: AnnotationIntent;
    text: string;
  },
) => api<Annotation>(`/projects/${id}/annotations`, { method: "POST", body: JSON.stringify(body) });
export const listAnnotations = (id: string) => api<Annotation[]>(`/projects/${id}/annotations`);
// LONG-tier chapter outline (empty for short/medium)
export const getOutline = (id: string) => api<Act[]>(`/projects/${id}/plan/outline`);
export const resolveAnnotation = (id: string, annId: string) =>
  api<Annotation>(`/projects/${id}/annotations/${annId}/resolve`, { method: "POST" });
export const directorChat = (id: string, message: string) =>
  api<DirectorResponse>(`/projects/${id}/director`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
export const directorTurns = (id: string) => api<DirectorTurn[]>(`/projects/${id}/director/turns`);

// long-source import (script / novel / transcript -> scenes + cast)
export const importSource = (id: string, text: string, replace = false) =>
  api<{ events: number; scenes: number; cast: string[]; logline: string }>(
    `/projects/${id}/import-source`,
    { method: "POST", body: JSON.stringify({ text, replace }) },
  );
export const listVersions = (id: string, shotId: string) =>
  api<ShotVersion[]>(`/projects/${id}/shots/${shotId}/versions`);
export const selectVersion = (id: string, shotId: string, versionId: string) =>
  api<ShotVersion>(`/projects/${id}/shots/${shotId}/versions/${versionId}/select`, { method: "POST" });
export const editVersion = (id: string, shotId: string, versionId: string, instruction: string) =>
  api<ShotVersion>(`/projects/${id}/shots/${shotId}/versions/${versionId}/edit`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
export const reviewVersion = (id: string, shotId: string, versionId: string) =>
  api<ShotVersion>(`/projects/${id}/shots/${shotId}/versions/${versionId}/review`, {
    method: "POST",
  });
export const refreshJob = (id: string, jobId: string) =>
  api<ShotVersion>(`/projects/${id}/jobs/${jobId}/refresh`, { method: "POST" });
export const listJobs = (id: string) => api<Job[]>(`/projects/${id}/jobs`);
export const retryJob = (id: string, jobId: string) =>
  api<ShotVersion>(`/projects/${id}/jobs/${jobId}/retry`, { method: "POST" });

export const assembleRoughCut = (
  id: string,
  opts?: { clips?: ClipSpec[]; captions?: boolean; music?: boolean; voiceover?: boolean },
) =>
  api<RoughCut>(`/projects/${id}/rough-cut`, {
    method: "POST",
    body: JSON.stringify(opts ?? {}),
  });
export const listRoughCuts = (id: string) => api<RoughCut[]>(`/projects/${id}/rough-cut`);

export const listCharacters = (id: string) => api<Character[]>(`/projects/${id}/characters`);
export const listStylePacks = (id: string) => api<StylePack[]>(`/projects/${id}/style-packs`);

export type Usage = {
  videos_today: number;
  images_today: number;
  audio_today: number;
  video_cap: number;
  image_cap: number;
  audio_cap: number;
  failed_today: number;
  est_spend_usd: number;
};
export const getUsage = () => api<Usage>("/usage");
