"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  assembleRoughCut,
  deleteProject,
  editVersion,
  generateAllKeyframes,
  generateAllShots,
  generateImages,
  generateKeyframe,
  generateShot,
  generateVoiceover,
  getConceptSets,
  getProject,
  getScript,
  getStoryboard,
  listCharacters,
  listJobs,
  listRoughCuts,
  listVersions,
  promoteFrame,
  publishCut,
  refineFrame,
  retryJob,
  reviewVersion,
  selectVersion,
  unpublishCut,
  updateShot,
  type Character,
  type ClipSpec,
  type ConceptSet,
  type Job,
  type Project,
  type RoughCut,
  type Scene,
  type Shot,
  type ShotUpdate,
  type ShotVersion,
} from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import { Alert, Button, cn, Drawer, Eyebrow, Pill, StageRail, Tabs, type TabItem } from "@/components/ui";
import PlanPanel from "@/components/workspace/PlanPanel";
import LookBoard from "@/components/workspace/LookBoard";
import ReviewPanel from "@/components/workspace/ReviewPanel";
import ShotBoard from "@/components/workspace/ShotBoard";
import ShotInspector from "@/components/workspace/ShotInspector";
import CutPlanner from "@/components/workspace/CutPlanner";
import QueueDock from "@/components/workspace/QueueDock";
import TimelineStrip from "@/components/workspace/TimelineStrip";
import AutonomyToggle from "@/components/workspace/AutonomyToggle";
import CastPanel from "@/components/workspace/CastPanel";
import DirectorPanel from "@/components/workspace/DirectorPanel";
import { PROJECTS_CHANGED } from "@/components/Sidebar";
import {
  aspectClass,
  errMsg,
  isPlayable,
  isRendered,
  isRunning,
  usageChanged,
} from "@/components/workspace/shared";

// The six pipeline stages — the canvas regions. Director (right rail) and Queue (footer dock)
// are co-present surfaces, not stages, so they no longer live in this list.
type StageId = "plan" | "look" | "cast" | "review" | "shots" | "cut";
const STAGE_ORDER: StageId[] = ["plan", "look", "cast", "review", "shots", "cut"];

/** lg+ viewport — drives whether the rails dock as panes or open as drawers. */
function useIsDesktop() {
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const sync = () => setDesktop(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return desktop;
}

export default function Workspace({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [conceptSets, setConceptSets] = useState<ConceptSet[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [versions, setVersions] = useState<Record<string, ShotVersion[]>>({});
  const [roughCuts, setRoughCuts] = useState<RoughCut[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<StageId>("plan");
  const [inspected, setInspected] = useState<string | null>(null);
  const [directorOpen, setDirectorOpen] = useState(false); // mobile director drawer
  const [rightCollapsed, setRightCollapsed] = useState(false); // desktop right rail collapse
  const [scopedShotIds, setScopedShotIds] = useState<string[]>([]); // director scope: shots
  const [scopedCastIds, setScopedCastIds] = useState<string[]>([]); // director scope: cast
  const [boardView, setBoardView] = useState<"board" | "sequence">("board"); // storyboard altitude
  const [assembling, setAssembling] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [generating, setGenerating] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [announce, setAnnounce] = useState("");
  // project actions (⋯) menu + delete confirmation
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);

  const aspect = project?.aspect_ratio ?? "9:16";
  const isDesktop = useIsDesktop();
  const readyRef = useRef<Set<string>>(new Set());
  const tabInitRef = useRef(false);

  const loadVersions = useCallback(
    async (shotList: Shot[]) => {
      const entries = await Promise.all(
        shotList.map(async (s) => [s.id, await listVersions(projectId, s.id)] as const),
      );
      setVersions(Object.fromEntries(entries));
      // resume polling for jobs still running after a refresh
      setGenerating(entries.filter(([, vs]) => vs.some(isRunning)).map(([id]) => id));
      readyRef.current = new Set(
        entries.filter(([, vs]) => vs.some((v) => v.output_asset_id)).map(([id]) => id),
      );
    },
    [projectId],
  );

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await listJobs(projectId));
    } catch {
      /* queue is best-effort; the next poll retries */
    }
  }, [projectId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, sc, sb, cs, rc, ch] = await Promise.all([
        getProject(projectId),
        getScript(projectId),
        getStoryboard(projectId),
        getConceptSets(projectId),
        listRoughCuts(projectId),
        listCharacters(projectId),
      ]);
      setProject(p);
      setScenes(sc);
      setShots(sb);
      setConceptSets(cs);
      setRoughCuts(rc);
      setCharacters(ch);
      if (sb.length) await loadVersions(sb);
      await loadJobs();
      if (!tabInitRef.current) {
        tabInitRef.current = true;
        setTab(sb.length ? "shots" : "plan");
      }
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, loadVersions, loadJobs]);

  useEffect(() => {
    // microtask defer keeps the effect body free of synchronous state updates
    void Promise.resolve().then(loadAll);
  }, [loadAll]);

  // number keys 1-6 jump between stages (unless typing)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
      const i = ["1", "2", "3", "4", "5", "6"].indexOf(e.key);
      if (i >= 0) setTab(STAGE_ORDER[i]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // live job-progress stream (SSE) — refetch the affected shot the instant a take changes
  // state, instead of waiting for the next poll. Additive: the 5s poll stays the fallback.
  useEffect(() => {
    const ctrl = new AbortController();
    streamSSE(`/projects/${projectId}/events`, {
      signal: ctrl.signal,
      onEvent: async (e) => {
        if (e.type !== "job" || typeof e.shot_id !== "string") return;
        const sid = e.shot_id;
        try {
          const vs = await listVersions(projectId, sid);
          setVersions((v) => ({ ...v, [sid]: vs }));
          if (vs.some(isRunning)) setGenerating((g) => (g.includes(sid) ? g : [...g, sid]));
          loadJobs();
        } catch {
          /* the poll will catch up */
        }
      },
    }).catch(() => {
      /* SSE is additive; the poll remains the source of truth */
    });
    return () => ctrl.abort();
  }, [projectId, loadJobs]);

  // poll generating shots (resilient: one failed/404 id never strands the others);
  // the interval restarts when the generating set changes, so the closure stays fresh
  const generatingKey = generating.join(",");
  useEffect(() => {
    if (!generatingKey) return;
    const ids = generatingKey.split(",");
    const t = setInterval(async () => {
      try {
        const settled = await Promise.allSettled(ids.map((id) => listVersions(projectId, id)));
        const fulfilled: Record<string, ShotVersion[]> = {};
        const keep: string[] = [];
        settled.forEach((r, i) => {
          const id = ids[i];
          if (r.status === "fulfilled") {
            fulfilled[id] = r.value;
            if (r.value.some(isRunning)) keep.push(id);
            if (r.value.some((v) => v.output_asset_id) && !readyRef.current.has(id)) {
              readyRef.current.add(id);
              setAnnounce("A shot finished rendering.");
            }
          } else {
            keep.push(id); // transient failure — keep polling instead of stranding
          }
        });
        if (Object.keys(fulfilled).length) setVersions((v) => ({ ...v, ...fulfilled }));
        setGenerating((g) => g.filter((id) => keep.includes(id)));
        loadJobs();
      } catch (e) {
        setError(errMsg(e));
      }
    }, 5000);
    return () => clearInterval(t);
  }, [generatingKey, projectId, loadJobs]);

  // ── actions ──────────────────────────────────────────────────────────────

  async function genImages(csId: string) {
    setBusy((b) => ({ ...b, [csId]: true }));
    setError(null);
    try {
      await generateImages(projectId, csId);
      setConceptSets(await getConceptSets(projectId));
      usageChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy((b) => ({ ...b, [csId]: false }));
    }
  }

  async function promote(frameId: string, target: string) {
    setError(null);
    try {
      await promoteFrame(projectId, frameId, target);
      const [cs, ch] = await Promise.all([getConceptSets(projectId), listCharacters(projectId)]);
      setConceptSets(cs);
      setCharacters(ch);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function refine(frameId: string, instruction: string) {
    setError(null);
    try {
      await refineFrame(projectId, frameId, instruction);
      setConceptSets(await getConceptSets(projectId));
      usageChanged();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function refreshShot(shotId: string) {
    const vs = await listVersions(projectId, shotId);
    setVersions((v) => ({ ...v, [shotId]: vs }));
    if (vs.some(isRunning)) setGenerating((g) => (g.includes(shotId) ? g : [...g, shotId]));
  }

  async function genShot(
    shotId: string,
    opts?: { character_id?: string; continue_from_previous?: boolean; num_takes?: number },
  ) {
    setBusy((b) => ({ ...b, [shotId]: true }));
    setError(null);
    try {
      await generateShot(projectId, shotId, opts);
      await refreshShot(shotId);
      usageChanged();
      loadJobs();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy((b) => ({ ...b, [shotId]: false }));
    }
  }

  const [batchBusy, setBatchBusy] = useState<string | null>(null);

  async function genKeyframe(shotId: string) {
    setBusy((b) => ({ ...b, [shotId]: true }));
    setError(null);
    try {
      await generateKeyframe(projectId, shotId);
      setShots(await getStoryboard(projectId));
      usageChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy((b) => ({ ...b, [shotId]: false }));
    }
  }

  async function genVoiceover(shotId: string) {
    setBusy((b) => ({ ...b, [shotId]: true }));
    setError(null);
    try {
      await generateVoiceover(projectId, shotId);
      setShots(await getStoryboard(projectId));
      usageChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy((b) => ({ ...b, [shotId]: false }));
    }
  }

  async function genAllKeyframes() {
    setBatchBusy("keyframes");
    setError(null);
    try {
      await generateAllKeyframes(projectId);
      setShots(await getStoryboard(projectId));
      usageChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBatchBusy(null);
    }
  }

  async function renderAll(chained: boolean) {
    setBatchBusy(chained ? "render-chained" : "render");
    setError(null);
    try {
      await generateAllShots(projectId, chained);
      await loadVersions(shots);
      usageChanged();
      await loadJobs();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBatchBusy(null);
    }
  }

  async function genEdit(shotId: string, versionId: string, instruction: string) {
    if (!instruction.trim()) return;
    setBusy((b) => ({ ...b, [shotId]: true }));
    setError(null);
    try {
      await editVersion(projectId, shotId, versionId, instruction.trim());
      await refreshShot(shotId);
      usageChanged();
      loadJobs();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy((b) => ({ ...b, [shotId]: false }));
    }
  }

  async function patchShot(shotId: string, patch: ShotUpdate) {
    setError(null);
    try {
      await updateShot(projectId, shotId, patch);
      setShots(await getStoryboard(projectId));
    } catch (e) {
      setError(errMsg(e));
      throw e; // the inspector shows the failure inline and keeps the dirty draft
    }
  }

  async function pickVersion(shotId: string, versionId: string) {
    setVersions((v) => ({
      ...v,
      [shotId]: (v[shotId] ?? []).map((x) => ({ ...x, selected: x.id === versionId })),
    }));
    try {
      await selectVersion(projectId, shotId, versionId);
    } catch (e) {
      setError(errMsg(e));
      loadVersions(shots);
    }
  }

  async function reviewNow(shotId: string, versionId: string) {
    setError(null);
    try {
      await reviewVersion(projectId, shotId, versionId);
      await refreshShot(shotId);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function retry(jobId: string) {
    setError(null);
    try {
      const v = await retryJob(projectId, jobId);
      await refreshShot(v.shot_id);
      usageChanged();
      await loadJobs();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function assemble(
    clips: ClipSpec[],
    captions: boolean,
    music: boolean,
    voiceover: boolean,
  ) {
    setAssembling(true);
    setError(null);
    try {
      await assembleRoughCut(projectId, { clips, captions, music, voiceover });
      setRoughCuts(await listRoughCuts(projectId));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setAssembling(false);
    }
  }

  async function togglePublish(rc: RoughCut) {
    setPublishing(rc.id);
    setError(null);
    try {
      if (rc.published) await unpublishCut(projectId, rc.id);
      else await publishCut(projectId, rc.id);
      setRoughCuts(await listRoughCuts(projectId));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setPublishing(null);
    }
  }

  async function doDelete() {
    if (!project || confirmText.trim() !== project.title.trim() || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteProject(projectId);
      window.dispatchEvent(new Event(PROJECTS_CHANGED));
      router.push("/");
    } catch (e) {
      setError(errMsg(e));
      setDeleting(false);
    }
  }

  // ── director scope (select-to-scope) ──────────────────────────────────────
  // toggling always surfaces the director (close the inspector, expand the rail) so the
  // freshly-pinned chip is visible; sending an instruction clears the scope.
  function toggleShotScope(id: string) {
    setInspected(null);
    setRightCollapsed(false);
    setScopedShotIds((xs) => (xs.includes(id) ? xs.filter((x) => x !== id) : [...xs, id]));
  }
  function toggleCastScope(id: string) {
    setInspected(null);
    setRightCollapsed(false);
    setScopedCastIds((xs) => (xs.includes(id) ? xs.filter((x) => x !== id) : [...xs, id]));
  }
  function clearScope() {
    setScopedShotIds([]);
    setScopedCastIds([]);
  }
  function removeChip(key: string) {
    const [kind, id] = key.split(":");
    if (kind === "shot") setScopedShotIds((xs) => xs.filter((x) => x !== id));
    else setScopedCastIds((xs) => xs.filter((x) => x !== id));
  }

  // ── derived ──────────────────────────────────────────────────────────────

  const planned = shots.length > 0;
  const renderedShots = shots.filter((s) => isRendered(versions[s.id] ?? [])).length;
  const generatedSets = conceptSets.filter((c) => c.status !== "planned").length;
  const mockMode = shots.some((s) =>
    (versions[s.id] ?? []).some((v) => v.output_asset_id && !isPlayable(v.video_url)),
  );

  const inspectedShot = shots.find((s) => s.id === inspected) ?? null;
  const canContinue = (() => {
    if (!inspectedShot || inspectedShot.order === 0) return false;
    const prev = shots.find((s) => s.order === inspectedShot.order - 1);
    return !!prev && isRendered(versions[prev.id] ?? []);
  })();

  // the pipeline stages, as a navigable map (shared by the desktop StageRail and the mobile Tabs)
  const stageTabs: TabItem[] = [
    {
      id: "plan",
      label: "Plan",
      meta: scenes.length ? `${scenes.length} sc` : undefined,
      done: scenes.length > 0,
    },
    {
      id: "look",
      label: "Look",
      meta: conceptSets.length ? `${generatedSets}/${conceptSets.length}` : undefined,
      done: generatedSets > 0,
      locked: scenes.length === 0,
    },
    {
      id: "cast",
      label: "Cast",
      meta: characters.length || undefined,
      done: characters.length > 0,
      locked: scenes.length === 0,
    },
    {
      id: "review",
      label: "Review",
      meta: shots.length || undefined,
      locked: shots.length === 0,
    },
    {
      id: "shots",
      label: "Storyboard",
      meta: shots.length ? `${renderedShots}/${shots.length}` : undefined,
      done: renderedShots > 0,
      locked: shots.length === 0,
    },
    {
      id: "cut",
      label: "Cut",
      meta: roughCuts.length || undefined,
      done: roughCuts.length > 0,
      locked: renderedShots === 0,
    },
  ];

  const inspectorEl = inspectedShot ? (
    <ShotInspector
      docked={isDesktop}
      key={inspectedShot.id}
      shot={inspectedShot}
      versions={versions[inspectedShot.id] ?? []}
      characters={characters}
      aspect={aspect}
      canContinue={canContinue}
      busy={!!busy[inspectedShot.id] || generating.includes(inspectedShot.id)}
      onClose={() => setInspected(null)}
      onGenerate={(opts) => genShot(inspectedShot.id, opts)}
      onEdit={(versionId, instruction) => genEdit(inspectedShot.id, versionId, instruction)}
      onPick={(versionId) => pickVersion(inspectedShot.id, versionId)}
      onReview={(versionId) => reviewNow(inspectedShot.id, versionId)}
      onUpdate={(patch) => patchShot(inspectedShot.id, patch)}
      onKeyframe={() => genKeyframe(inspectedShot.id)}
      onVoiceover={() => genVoiceover(inspectedShot.id)}
    />
  ) : null;

  const scopeChips: { key: string; label: string; ref: string }[] = [
    ...scopedShotIds.flatMap((id) => {
      const s = shots.find((x) => x.id === id);
      return s
        ? [{ key: `shot:${id}`, label: `@shot ${s.order + 1}`, ref: `shot ${s.order + 1}` }]
        : [];
    }),
    ...scopedCastIds.flatMap((id) => {
      const c = characters.find((x) => x.id === id);
      return c ? [{ key: `cast:${id}`, label: `@${c.name}`, ref: `the character ${c.name}` }] : [];
    }),
  ];

  const director = (
    <DirectorPanel
      projectId={projectId}
      onChanged={loadAll}
      scopeChips={scopeChips}
      onRemoveChip={removeChip}
      onClearScope={clearScope}
    />
  );

  // initial load / fatal error states
  if (loading && !project) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <div className="h-9 w-64 rounded shimmer" />
        <div className="mt-3 h-8 w-96 max-w-full rounded shimmer" />
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className={`${aspectClass("9:16")} rounded-[var(--radius)] shimmer`} />
          ))}
        </div>
      </main>
    );
  }
  if (!loading && error && !project) {
    return (
      <main className="mx-auto max-w-md px-4 py-24 text-center sm:px-6">
        <Alert>{error}</Alert>
        <div className="mt-5 flex justify-center gap-3">
          <Button onClick={loadAll}>Retry</Button>
          <Link href="/">
            <Button variant="ghost">← Projects</Button>
          </Link>
        </div>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col lg:h-full lg:overflow-hidden">
      <div aria-live="polite" className="sr-only">
        {announce}
      </div>

      {/* header — spans the full width above the editing room.
          `relative z-40` while the ⋯ menu is open so its dropdown clears the sticky rails. */}
      <header
        className={`flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border px-4 py-3 sm:px-6 ${
          menuOpen ? "relative z-40" : ""
        }`}
      >
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Link
            href="/"
            aria-label="Back to projects"
            className="-ml-2 inline-flex size-10 shrink-0 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-accent"
          >
            ←
          </Link>
          <div className="min-w-0">
            <Eyebrow>{project?.status ?? "—"}</Eyebrow>
            <h1 className="title truncate text-2xl text-fg sm:text-3xl">{project?.title ?? "…"}</h1>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {project && (
            <AutonomyToggle
              projectId={projectId}
              value={project.autonomy ?? "co"}
              onChange={(v) => setProject((p) => (p ? { ...p, autonomy: v } : p))}
            />
          )}
          <Pill>{aspect}</Pill>
          <Pill>{project?.target_duration_sec ?? "—"}s</Pill>
          {planned && (
            <Pill>
              {renderedShots}/{shots.length} shots
            </Pill>
          )}
          {/* mobile: open the director as a drawer (it lives in the right rail on desktop) */}
          <button
            type="button"
            onClick={() => setDirectorOpen(true)}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-[var(--radius)] border border-border bg-panel px-2.5 font-mono text-xs text-muted transition-colors hover:border-accent/40 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
          >
            Director
          </button>
          {/* project actions */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              aria-label="Project actions"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className="inline-flex size-9 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              ⋯
            </button>
            {menuOpen && (
              <>
                <button
                  type="button"
                  aria-hidden
                  tabIndex={-1}
                  onClick={() => setMenuOpen(false)}
                  className="fixed inset-0 z-40 cursor-default"
                />
                <div
                  role="menu"
                  className="absolute right-0 z-50 mt-1 w-44 overflow-hidden rounded-[var(--radius)] bg-elevated ring-1 ring-border-hi"
                >
                  <button
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      setConfirmText("");
                      setConfirmDelete(true);
                    }}
                    className="block w-full px-3 py-2 text-left text-sm text-fail transition-colors hover:bg-fail/10 focus-visible:outline-none focus-visible:bg-fail/10"
                  >
                    Delete project
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {error && (
        <div className="px-4 pt-4 sm:px-6">
          <Alert>{error}</Alert>
        </div>
      )}

      {mockMode && (
        <div className="px-4 pt-4 sm:px-6">
          <div className="flex items-center gap-2 rounded-[var(--radius)] border border-border-hi bg-bg-soft px-3 py-2 text-xs text-muted">
            <Pill>mock mode</Pill>
            <span>Videos are simulated — previews are unavailable, but the full workflow runs.</span>
          </div>
        </div>
      )}

      {/* three-zone editing room: stage map · canvas (hero) · director rail */}
      <div className="flex min-h-0 flex-1">
        {/* stage map (desktop) */}
        {isDesktop && (
          <aside className="hidden h-full w-44 shrink-0 flex-col overflow-y-auto border-r border-border bg-bg-soft/40 px-2 py-4 lg:flex">
            <p className="eyebrow px-2 pb-2">Stages</p>
            <StageRail stages={stageTabs} active={tab} onSelect={(id) => setTab(id as StageId)} />
          </aside>
        )}

        {/* canvas */}
        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          {/* mobile stage bar */}
          {!isDesktop && (
            <div className="sticky top-0 z-20 border-b border-border bg-bg/85 px-4 py-2 backdrop-blur">
              <Tabs active={tab} onSelect={(id) => setTab(id as StageId)} tabs={stageTabs} />
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 pb-10 sm:px-6">
            {tab === "plan" && (
              <PlanPanel
                projectId={projectId}
                planned={planned}
                scenes={scenes}
                conceptSets={conceptSets}
                onPlanned={async () => {
                  setGenerating([]);
                  setBusy({});
                  await loadAll();
                  // land on the review gate: show the full plan + cost before any spend
                  setTab("review");
                }}
                onRefresh={loadAll}
              />
            )}
            {tab === "look" && (
              <LookBoard
                conceptSets={conceptSets}
                aspect={aspect}
                busy={busy}
                onGenerate={genImages}
                onPromote={promote}
                onRefine={refine}
              />
            )}
            {tab === "cast" && (
              <CastPanel
                projectId={projectId}
                characters={characters}
                hasScript={scenes.length > 0}
                onChanged={async () => setCharacters(await listCharacters(projectId))}
              />
            )}
            {tab === "review" && (
              <ReviewPanel projectId={projectId} scenes={scenes} shots={shots} onRefresh={loadAll} />
            )}
            {tab === "shots" && (
              <div className="space-y-4">
                {shots.length > 0 && (
                  <div className="inline-flex rounded-[var(--radius)] border border-border bg-bg-soft p-0.5 font-mono text-xs">
                    {(["board", "sequence"] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setBoardView(v)}
                        aria-pressed={boardView === v}
                        className={cn(
                          "rounded-[calc(var(--radius)-0.2rem)] px-3 py-1 capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                          boardView === v ? "bg-panel-hi text-accent" : "text-muted hover:text-fg",
                        )}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                )}
                {boardView === "sequence" && shots.length > 0 ? (
                  <TimelineStrip
                    shots={shots}
                    scenes={scenes}
                    versions={versions}
                    scopedShotIds={scopedShotIds}
                    onOpen={setInspected}
                    onToggleShotScope={toggleShotScope}
                  />
                ) : (
                  <ShotBoard
                    shots={shots}
                    scenes={scenes}
                    versions={versions}
                    characters={characters}
                    aspect={aspect}
                    busy={busy}
                    generating={generating}
                    batchBusy={batchBusy}
                    projectId={projectId}
                    budgetUsd={project?.budget_usd}
                    scopedShotIds={scopedShotIds}
                    scopedCastIds={scopedCastIds}
                    onOpen={setInspected}
                    onGenerate={(shotId) => genShot(shotId)}
                    onKeyframes={genAllKeyframes}
                    onRenderAll={renderAll}
                    onToggleShotScope={toggleShotScope}
                    onToggleCastScope={toggleCastScope}
                  />
                )}
              </div>
            )}
            {tab === "cut" && (
              <CutPlanner
                shots={shots}
                versions={versions}
                roughCuts={roughCuts}
                aspect={aspect}
                assembling={assembling}
                publishing={publishing}
                onAssemble={assemble}
                onTogglePublish={togglePublish}
              />
            )}
          </div>

          {/* queue — a persistent footer dock, not a tab */}
          <QueueDock jobs={jobs} onRetry={retry} />
        </main>

        {/* right rail (desktop): the inspected shot, else the persistent director */}
        {isDesktop &&
          (inspectedShot ? (
            <aside className="h-full w-[22rem] shrink-0 overflow-hidden border-l border-border bg-bg xl:w-[26rem]">
              {inspectorEl}
            </aside>
          ) : rightCollapsed ? (
            <button
              type="button"
              onClick={() => setRightCollapsed(false)}
              aria-label="Open director"
              className="flex h-full w-10 shrink-0 items-center justify-center border-l border-border bg-bg-soft/40 text-faint transition-colors hover:text-accent"
            >
              <span className="font-mono text-xs tracking-widest [writing-mode:vertical-rl]">
                Director
              </span>
            </button>
          ) : (
            <aside className="flex h-full w-[22rem] shrink-0 flex-col overflow-hidden border-l border-border bg-bg xl:w-[26rem]">
              <div className="flex shrink-0 items-center justify-end border-b border-border px-2 py-1.5">
                <button
                  type="button"
                  onClick={() => setRightCollapsed(true)}
                  aria-label="Collapse director"
                  title="Collapse director"
                  className="inline-flex size-7 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  →
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden px-4 pb-3">{director}</div>
            </aside>
          ))}
      </div>

      {/* mobile: inspector renders its own drawer (docked=false); director opens on demand */}
      {!isDesktop && inspectorEl}
      {!isDesktop && (
        <Drawer open={directorOpen} onClose={() => setDirectorOpen(false)} label="Director">
          <div className="flex h-full flex-col p-4">{director}</div>
        </Drawer>
      )}

      {confirmDelete && project && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={() => setConfirmDelete(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-[var(--radius)] border border-fail/30 bg-elevated p-6"
          >
            <h2 className="title text-xl text-fg">Delete this project?</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              This permanently deletes <span className="text-fg">“{project.title}”</span> — its
              scenes, shots, generated images and videos, and any cut. This can’t be undone.
            </p>
            <label className="mt-4 block">
              <span className="text-xs text-faint">
                Type <span className="font-mono text-fg">{project.title}</span> to confirm
              </span>
              <input
                autoFocus
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setConfirmDelete(false);
                  if (e.key === "Enter") doDelete();
                }}
                placeholder={project.title}
                className="mt-1 w-full rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                loading={deleting}
                disabled={confirmText.trim() !== project.title.trim()}
                onClick={doDelete}
              >
                Delete project
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
