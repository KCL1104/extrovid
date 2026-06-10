// Typed client for the extrovid backend. Browser-side; per-user Bearer token.

import { type AuthUser, clearAuth, getToken } from "@/lib/auth";

export type { AuthUser };

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "https://backend-production-8b09.up.railway.app/api";

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
};

export type Project = {
  id: string;
  title: string;
  owner_id: string;
  status: string;
  aspect_ratio: string;
  target_duration_sec: number;
  created_at: string;
  stats?: ProjectStats | null;
};

export type SceneBeat = { order: number; description: string; narration?: string | null; dialogue?: string | null };
export type Scene = { id: string; order: number; title: string; summary: string; beats: SceneBeat[]; est_duration_sec: number };

export type LookFrame = {
  id: string;
  prompt: string;
  tags: string[];
  promoted_as: string;
  selected: boolean;
  image_asset_id: string | null;
  image_url: string | null;
  parent_frame_id?: string | null;
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
};

export type ReviewSuggestion = { kind: "edit" | "retake"; instruction: string };
export type Review = {
  verdict: "pass" | "revise";
  score: number;
  notes: string[];
  suggestions: ReviewSuggestion[];
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
  options?: { captions?: boolean; music?: boolean } | null;
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

export type Character = { id: string; name: string; description: string | null; reference_image_urls: string[] };
export type StylePack = { id: string; label: string; image_urls: string[] };

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
export type VisualPlans = { visual_briefs: VisualBrief[]; concept_specs: unknown[] };

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
export const rotateToken = () => api<{ token: string }>("/auth/rotate-token", { method: "POST" });
export const logout = () => api<void>("/auth/logout", { method: "POST" });
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
  body: { title?: string; aspect_ratio?: string; target_duration_sec?: number } = {},
) => api<Project>("/projects", { method: "POST", body: JSON.stringify(body) });
export const getProject = (id: string) => api<Project>(`/projects/${id}`);
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

// per-stage planning (staged run console shows live progress per stage)
export const runBrief = (id: string, raw_prompt: string, clarifications: ClarifyAnswer[] = []) =>
  api<BriefInput>(`/projects/${id}/brief`, {
    method: "POST",
    body: JSON.stringify(clarifications.length ? { raw_prompt, clarifications } : { raw_prompt }),
  });
export const runScript = (id: string, brief: BriefInput) =>
  api<ScriptDraft>(`/projects/${id}/script`, { method: "POST", body: JSON.stringify(brief) });
export const runVisualBriefs = (id: string, script: ScriptDraft) =>
  api<VisualPlans>(`/projects/${id}/visual-briefs`, { method: "POST", body: JSON.stringify(script) });
export const runStoryboard = (
  id: string,
  script: ScriptDraft,
  concept_specs: unknown[],
  target_duration_sec: number,
) =>
  api<unknown>(`/projects/${id}/storyboard`, {
    method: "POST",
    body: JSON.stringify({ script, concept_specs, target_duration_sec }),
  });

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
    character_id?: string;
    continue_from_previous?: boolean;
  },
) =>
  api<ShotVersion>(`/projects/${id}/shots/${shotId}/generate`, {
    method: "POST",
    body: JSON.stringify(opts ?? {}),
  });
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
  opts?: { clips?: ClipSpec[]; captions?: boolean; music?: boolean },
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
  video_cap: number;
  image_cap: number;
  failed_today: number;
  est_spend_usd: number;
};
export const getUsage = () => api<Usage>("/usage");
