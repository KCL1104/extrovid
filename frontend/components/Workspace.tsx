"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  assembleRoughCut,
  editVersion,
  generateImages,
  generateShot,
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
import { Alert, Button, Eyebrow, Pill, Tabs } from "@/components/ui";
import UsageBadge from "@/components/UsageBadge";
import PlanPanel from "@/components/workspace/PlanPanel";
import LookBoard from "@/components/workspace/LookBoard";
import ShotBoard from "@/components/workspace/ShotBoard";
import ShotInspector from "@/components/workspace/ShotInspector";
import CutPlanner from "@/components/workspace/CutPlanner";
import QueuePanel from "@/components/workspace/QueuePanel";
import {
  aspectClass,
  errMsg,
  isPlayable,
  isRendered,
  isRunning,
  usageChanged,
} from "@/components/workspace/shared";

type TabId = "plan" | "look" | "shots" | "cut" | "queue";
const TAB_ORDER: TabId[] = ["plan", "look", "shots", "cut", "queue"];

export default function Workspace({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [conceptSets, setConceptSets] = useState<ConceptSet[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [versions, setVersions] = useState<Record<string, ShotVersion[]>>({});
  const [roughCuts, setRoughCuts] = useState<RoughCut[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<TabId>("plan");
  const [inspected, setInspected] = useState<string | null>(null);
  const [assembling, setAssembling] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [generating, setGenerating] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [announce, setAnnounce] = useState("");

  const aspect = project?.aspect_ratio ?? "9:16";
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

  // number keys 1-5 jump between workspaces (unless typing)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
      const i = ["1", "2", "3", "4", "5"].indexOf(e.key);
      if (i >= 0) setTab(TAB_ORDER[i]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    opts?: { character_id?: string; continue_from_previous?: boolean },
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

  async function assemble(clips: ClipSpec[], captions: boolean, music: boolean) {
    setAssembling(true);
    setError(null);
    try {
      await assembleRoughCut(projectId, { clips, captions, music });
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

  // ── derived ──────────────────────────────────────────────────────────────

  const planned = shots.length > 0;
  const renderedShots = shots.filter((s) => isRendered(versions[s.id] ?? [])).length;
  const generatedSets = conceptSets.filter((c) => c.status !== "planned").length;
  const runningJobs = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
  const mockMode = shots.some((s) =>
    (versions[s.id] ?? []).some((v) => v.output_asset_id && !isPlayable(v.video_url)),
  );

  const inspectedShot = shots.find((s) => s.id === inspected) ?? null;
  const canContinue = (() => {
    if (!inspectedShot || inspectedShot.order === 0) return false;
    const prev = shots.find((s) => s.order === inspectedShot.order - 1);
    return !!prev && isRendered(versions[prev.id] ?? []);
  })();

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
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
      <div aria-live="polite" className="sr-only">
        {announce}
      </div>

      {/* header */}
      <div className="rise flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <Link
            href="/"
            aria-label="Back to projects"
            className="-ml-2 inline-flex size-10 shrink-0 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-accent"
          >
            ←
          </Link>
          <div className="min-w-0">
            <Eyebrow>{project?.status ?? "—"}</Eyebrow>
            <h1 className="title truncate text-3xl text-fg">{project?.title ?? "…"}</h1>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Pill>{aspect}</Pill>
          <Pill>{project?.target_duration_sec ?? "—"}s</Pill>
          {planned && (
            <Pill>
              {renderedShots}/{shots.length} shots
            </Pill>
          )}
          <UsageBadge />
        </div>
      </div>

      {error && (
        <div className="mt-4">
          <Alert>{error}</Alert>
        </div>
      )}

      {mockMode && (
        <div className="mt-4 flex items-center gap-2 rounded-[var(--radius)] border border-border-hi bg-bg-soft px-3 py-2 text-xs text-muted">
          <Pill>mock mode</Pill>
          <span>Videos are simulated — previews are unavailable, but the full workflow runs.</span>
        </div>
      )}

      {/* stage tabs */}
      <div className="sticky top-0 z-30 -mx-4 mt-6 border-b border-border bg-bg/85 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6">
        <Tabs
          active={tab}
          onSelect={(id) => setTab(id as TabId)}
          tabs={[
            { id: "plan", label: "Plan", meta: scenes.length ? `${scenes.length} sc` : undefined },
            {
              id: "look",
              label: "Look",
              meta: conceptSets.length ? `${generatedSets}/${conceptSets.length}` : undefined,
            },
            {
              id: "shots",
              label: "Storyboard",
              meta: shots.length ? `${renderedShots}/${shots.length}` : undefined,
            },
            { id: "cut", label: "Cut", meta: roughCuts.length || undefined },
            {
              id: "queue",
              label: "Queue",
              meta: jobs.length || undefined,
              live: runningJobs > 0,
            },
          ]}
        />
      </div>

      <div className="mt-6 pb-24">
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
              setTab("look");
            }}
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
        {tab === "shots" && (
          <ShotBoard
            shots={shots}
            versions={versions}
            characters={characters}
            aspect={aspect}
            busy={busy}
            generating={generating}
            onOpen={setInspected}
            onGenerate={(shotId) => genShot(shotId)}
          />
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
        {tab === "queue" && <QueuePanel jobs={jobs} onRetry={retry} />}
      </div>

      {inspectedShot && (
        <ShotInspector
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
        />
      )}
    </main>
  );
}
