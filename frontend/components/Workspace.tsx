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
  getStoryboard,
  listCharacters,
  listRoughCuts,
  listVersions,
  promoteFrame,
  publishCut,
  runPipeline,
  selectVersion,
  unpublishCut,
  type Character,
  type ConceptSet,
  type Project,
  type RoughCut,
  type Shot,
  type ShotVersion,
} from "@/lib/api";
import { Alert, Button, Eyebrow, Panel, Pill, Spinner, StatusBadge } from "@/components/ui";
import UsageBadge from "@/components/UsageBadge";

const usageChanged = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("extrovid-usage-changed"));
};

function aspectClass(aspect: string) {
  return (
    { "9:16": "aspect-[9/16]", "16:9": "aspect-video", "1:1": "aspect-square", "4:5": "aspect-[4/5]" }[
      aspect
    ] ?? "aspect-video"
  );
}

// mock:// URLs (and anything non-http) are not playable/renderable.
const isPlayable = (u?: string | null): u is string => !!u && /^https?:/i.test(u);
const isRunning = (v: ShotVersion) => v.job_status === "running" || v.job_status === "queued";
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

const EXAMPLE_BRIEFS = [
  "A 20s vertical teaser for a specialty coffee brand — warm, energetic, ends on the logo.",
  "A 15s moody product reveal for a minimalist watch — slow push-in on the dial.",
];

export default function Workspace({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [conceptSets, setConceptSets] = useState<ConceptSet[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [versions, setVersions] = useState<Record<string, ShotVersion[]>>({});
  const [roughCuts, setRoughCuts] = useState<RoughCut[]>([]);
  const [brief, setBrief] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [generating, setGenerating] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [announce, setAnnounce] = useState("");

  const aspect = project?.aspect_ratio ?? "9:16";
  const shotsRef = useRef<Shot[]>([]);
  shotsRef.current = shots;
  const genRef = useRef<string[]>([]);
  genRef.current = generating;
  const readyRef = useRef<Set<string>>(new Set());

  const loadVersions = useCallback(
    async (shotList: Shot[]) => {
      const entries = await Promise.all(
        shotList.map(async (s) => [s.id, await listVersions(projectId, s.id)] as const),
      );
      setVersions(Object.fromEntries(entries));
      // resume polling for jobs still running after a refresh
      setGenerating(entries.filter(([, vs]) => vs.some(isRunning)).map(([id]) => id));
      readyRef.current = new Set(
        entries.filter(([, vs]) => vs.some((v) => isPlayable(v.video_url))).map(([id]) => id),
      );
    },
    [projectId],
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, sb, cs, rc, ch] = await Promise.all([
        getProject(projectId),
        getStoryboard(projectId),
        getConceptSets(projectId),
        listRoughCuts(projectId),
        listCharacters(projectId),
      ]);
      setProject(p);
      setShots(sb);
      setConceptSets(cs);
      setRoughCuts(rc);
      setCharacters(ch);
      if (sb.length) await loadVersions(sb);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, loadVersions]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // elapsed counter while the plan runs
  useEffect(() => {
    if (!running) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  // poll generating shots (resilient: one failed/404 id never strands the others)
  const isPolling = generating.length > 0;
  useEffect(() => {
    if (!isPolling) return;
    const t = setInterval(async () => {
      try {
        const ids = genRef.current;
        const settled = await Promise.allSettled(ids.map((id) => listVersions(projectId, id)));
        const fulfilled: Record<string, ShotVersion[]> = {};
        const keep: string[] = [];
        settled.forEach((r, i) => {
          const id = ids[i];
          if (r.status === "fulfilled") {
            fulfilled[id] = r.value;
            if (r.value.some(isRunning)) keep.push(id);
            if (r.value.some((v) => isPlayable(v.video_url)) && !readyRef.current.has(id)) {
              readyRef.current.add(id);
              setAnnounce("A shot finished rendering.");
            }
          } else {
            keep.push(id); // transient failure — keep polling instead of stranding
          }
        });
        if (Object.keys(fulfilled).length) setVersions((v) => ({ ...v, ...fulfilled }));
        setGenerating((g) => g.filter((id) => keep.includes(id)));
      } catch (e) {
        setError(errMsg(e));
      }
    }, 5000);
    return () => clearInterval(t);
  }, [isPolling, projectId]);

  async function run() {
    if (running) return;
    setConfirmReplace(false);
    setRunning(true);
    setError(null);
    try {
      await runPipeline(projectId, brief.trim());
      setGenerating([]);
      setBusy({});
      await loadAll();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setRunning(false);
    }
  }
  function startRun() {
    if (!brief.trim() || running) return;
    if (planned) setConfirmReplace(true);
    else run();
  }

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

  async function genShot(shotId: string, characterId?: string) {
    setBusy((b) => ({ ...b, [shotId]: true }));
    setError(null);
    try {
      await generateShot(projectId, shotId, characterId ? { character_id: characterId } : undefined);
      const vs = await listVersions(projectId, shotId);
      setVersions((v) => ({ ...v, [shotId]: vs }));
      if (vs.some(isRunning)) setGenerating((g) => (g.includes(shotId) ? g : [...g, shotId]));
      usageChanged();
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
      const vs = await listVersions(projectId, shotId);
      setVersions((v) => ({ ...v, [shotId]: vs }));
      if (vs.some(isRunning)) setGenerating((g) => (g.includes(shotId) ? g : [...g, shotId]));
      usageChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy((b) => ({ ...b, [shotId]: false }));
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
      loadVersions(shotsRef.current);
    }
  }

  async function assemble() {
    setAssembling(true);
    setError(null);
    try {
      await assembleRoughCut(projectId);
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

  const planned = shots.length > 0;
  // A take is "rendered" once it has an output asset — true in BOTH mock and real mode.
  // Real mode: output_asset_id co-occurs with a playable url; mock: url is mock:// (not playable).
  // Matches the backend's assemble-eligibility (rough_cut_service._chosen filters output_asset_id),
  // so this unblocks Assemble in mock mode without changing real-mode behavior.
  const renderedShots = shots.filter((s) => (versions[s.id] ?? []).some((v) => v.output_asset_id)).length;
  const mockMode = shots.some((s) =>
    (versions[s.id] ?? []).some((v) => v.output_asset_id && !isPlayable(v.video_url)),
  );

  // initial load / fatal error states
  if (loading && !project) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="h-9 w-64 rounded shimmer" />
        <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className={`${aspectClass("9:16")} rounded-[var(--radius)] shimmer`} />
          ))}
        </div>
      </main>
    );
  }
  if (!loading && error && !project) {
    return (
      <main className="mx-auto max-w-md px-6 py-24 text-center">
        <Alert>{error}</Alert>
        <div className="mt-5 flex justify-center gap-3">
          <Button onClick={loadAll}>Retry</Button>
          <Link href="/"><Button variant="ghost">← Projects</Button></Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div aria-live="polite" className="sr-only">{announce}</div>

      {/* top bar */}
      <div className="rise flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <Link href="/" aria-label="Back to projects" className="shrink-0 text-faint transition-colors hover:text-accent">←</Link>
          <div className="min-w-0">
            <Eyebrow>{project?.status ?? "—"}</Eyebrow>
            <h1 className="title truncate text-3xl text-fg">{project?.title ?? "…"}</h1>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Pill>{aspect}</Pill>
          <Pill>{project?.target_duration_sec ?? "—"}s</Pill>
          {planned && <Pill>{renderedShots}/{shots.length} shots</Pill>}
          <UsageBadge />
        </div>
      </div>

      {error && <div className="mt-4"><Alert>{error}</Alert></div>}

      {mockMode && (
        <div className="mt-4 flex items-center gap-2 rounded-[var(--radius)] border border-border-hi bg-bg-soft px-3 py-2 text-xs text-muted">
          <Pill>mock mode</Pill>
          <span>Videos are simulated — previews are unavailable, but you can still assemble a cut.</span>
        </div>
      )}

      {/* brief */}
      <Panel className="rise mt-8 p-5">
        <Eyebrow>{planned ? "Re-brief" : "Brief"}</Eyebrow>
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="A 20s vertical teaser for a specialty coffee brand — warm, energetic, ends on the logo."
          rows={3}
          className="mt-3 w-full resize-none rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        />
        {confirmReplace ? (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-sm text-fail">Regenerating discards the current storyboard and any generated shot videos.</span>
            <Button variant="danger" onClick={run} loading={running}>Replace plan</Button>
            <Button variant="ghost" onClick={() => setConfirmReplace(false)}>Cancel</Button>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button variant="primary" onClick={startRun} loading={running} disabled={!brief.trim()}>
              {planned ? "Regenerate plan" : "Generate plan"}
            </Button>
            {running ? (
              <span className="font-mono text-xs text-run">Working… {elapsed}s · usually ~45s</span>
            ) : (
              <span className="text-xs text-faint">Writes script → previsual briefs → concept sets → shot list.</span>
            )}
          </div>
        )}
      </Panel>

      {/* onboarding — fresh project, no plan yet */}
      {!planned && !running && !loading && (
        <Panel className="rise mt-6 p-5">
          <Eyebrow>How it works</Eyebrow>
          <ol className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-xs text-muted">
            {["Brief", "Plan", "Concept images", "Generate shots", "Assemble cut"].map((step, i, a) => (
              <li key={step} className="flex items-center gap-2">
                <span className="text-accent">{i + 1}</span>
                <span>{step}</span>
                {i < a.length - 1 && <span className="text-faint">→</span>}
              </li>
            ))}
          </ol>
          {!brief.trim() && (
            <div className="mt-4">
              <span className="text-xs text-faint">Try an example brief:</span>
              <div className="mt-2 flex flex-col gap-2">
                {EXAMPLE_BRIEFS.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setBrief(ex)}
                    className="rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-left text-sm text-muted transition-colors hover:border-accent/40 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Panel>
      )}

      {/* plan-run skeleton */}
      {running && !planned && (
        <div className="mt-12 grid grid-cols-2 gap-4 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className={`${aspectClass(aspect)} rounded-[var(--radius)] shimmer`} />
          ))}
        </div>
      )}

      {planned && (
        <>
          {/* storyboard */}
          <section className="mt-12">
            <Eyebrow>Storyboard · {shots.length} shots</Eyebrow>
            <a
              href="#look-development"
              className="mt-1 inline-block font-mono text-[0.7rem] text-faint transition-colors hover:text-accent"
            >
              Tip: develop a look & promote a frame/character first — it feeds i2v and keeps shots consistent ↓
            </a>
            <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-3">
              {shots.map((shot, i) => (
                <ShotCard
                  key={shot.id}
                  shot={shot}
                  aspect={aspect}
                  versions={versions[shot.id] ?? []}
                  characters={characters}
                  busy={!!busy[shot.id]}
                  generating={generating.includes(shot.id)}
                  onGenerate={(characterId) => genShot(shot.id, characterId)}
                  onPick={(vid) => pickVersion(shot.id, vid)}
                  onEdit={(vid, instruction) => genEdit(shot.id, vid, instruction)}
                  delay={i * 40}
                />
              ))}
            </div>
          </section>

          {/* cast & style */}
          {characters.length > 0 && (
            <section className="mt-12">
              <Eyebrow>Cast & style · {characters.length}</Eyebrow>
              <div className="mt-4 flex flex-wrap gap-3">
                {characters.map((c) => (
                  <Panel key={c.id} className="flex items-center gap-3 p-2 pr-4">
                    <div className="size-12 shrink-0 overflow-hidden rounded-md bg-bg-soft">
                      {isPlayable(c.reference_image_urls[0]) && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={c.reference_image_urls[0]} alt={c.name} className="size-full object-cover" />
                      )}
                    </div>
                    <span className="text-sm text-fg">{c.name}</span>
                  </Panel>
                ))}
              </div>
              <p className="mt-2 text-xs text-faint">
                Attach a character when generating a shot to keep them consistent across shots (r2v).
              </p>
            </section>
          )}

          {/* look development */}
          <section id="look-development" className="mt-12 scroll-mt-6">
            <Eyebrow>Look development · {conceptSets.length} sets</Eyebrow>
            <p className="mt-1 text-xs text-faint">
              Promote a frame as <span className="text-fg">first frame</span> (auto-used by i2v shots) or{" "}
              <span className="text-fg">cast</span> (reusable character for r2v consistency).
            </p>
            <div className="mt-4 space-y-5">
              {conceptSets.map((cs, i) => (
                <ConceptSetCard
                  key={cs.id}
                  cs={cs}
                  aspect={aspect}
                  busy={!!busy[cs.id]}
                  onGenerate={() => genImages(cs.id)}
                  onPromote={promote}
                  delay={i * 40}
                />
              ))}
            </div>
          </section>

          {/* rough cut */}
          <section className="mb-24 mt-12">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Eyebrow>Rough cut</Eyebrow>
              <Button variant="primary" onClick={assemble} loading={assembling} disabled={renderedShots === 0}>
                Assemble rough cut
              </Button>
            </div>
            {renderedShots === 0 && (
              <p className="mt-3 text-sm text-faint">Generate at least one shot video to assemble a cut.</p>
            )}
            <div className="mt-4 space-y-4">
              {roughCuts.map((rc, i) => (
                <Panel key={rc.id} className="rise overflow-hidden p-4" style={{ animationDelay: `${i * 60}ms` }}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={rc.status} />
                      <Pill>{rc.shot_version_ids.length} shots</Pill>
                    </div>
                    {isPlayable(rc.video_url) && (
                      <div className="flex items-center gap-4">
                        <button
                          onClick={() => togglePublish(rc)}
                          disabled={publishing === rc.id}
                          className={`font-mono text-xs transition-colors disabled:opacity-50 ${
                            rc.published ? "text-ok hover:text-fail" : "text-muted hover:text-accent"
                          }`}
                        >
                          {publishing === rc.id
                            ? "…"
                            : rc.published
                              ? "● in gallery · unpublish"
                              : "share to gallery ↗"}
                        </button>
                        <a href={rc.video_url} target="_blank" rel="noreferrer" className="font-mono text-xs text-accent hover:underline">
                          download ↓
                        </a>
                      </div>
                    )}
                  </div>
                  {isPlayable(rc.video_url) ? (
                    <video
                      src={rc.video_url}
                      controls
                      className={`mt-3 ${aspectClass(aspect)} mx-auto max-h-[70vh] rounded-[var(--radius)] bg-black`}
                    />
                  ) : (
                    <p className="mt-3 font-mono text-xs text-faint">cut assembled — preview unavailable (mock mode)</p>
                  )}
                </Panel>
              ))}
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function ShotCard({
  shot,
  aspect,
  versions,
  characters,
  busy,
  generating,
  onGenerate,
  onPick,
  onEdit,
  delay,
}: {
  shot: Shot;
  aspect: string;
  versions: ShotVersion[];
  characters: Character[];
  busy: boolean;
  generating: boolean;
  onGenerate: (characterId?: string) => void;
  onPick: (versionId: string) => void;
  onEdit: (versionId: string, instruction: string) => void;
  delay: number;
}) {
  const [charId, setCharId] = useState("");
  const [editText, setEditText] = useState("");
  const [showEdit, setShowEdit] = useState(false);
  const withVideo = versions.filter((v) => isPlayable(v.video_url));
  const active = withVideo.find((v) => v.selected) ?? withVideo[withVideo.length - 1];
  const jobRunning = versions.some(isRunning);
  const busyState = generating || busy || jobRunning;
  const failed = !active && !busyState && versions.some((v) => v.job_status === "failed");
  const failedReason = versions.find((v) => v.job_status === "failed")?.failure_reason;
  const mockDone =
    !active && !busyState && !failed && versions.some((v) => v.output_asset_id && !isPlayable(v.video_url));
  const model = shot.preferred_model.replace("wan2.7-", "");
  const activeModel = active?.model?.split(":").pop()?.replace("wan2.7-", "");
  const genWith = () => onGenerate(charId || undefined);

  const picker = characters.length > 0 && (
    <div className="flex flex-wrap items-center justify-center gap-1.5">
      <span className="font-mono text-[0.6rem] text-faint">cast:</span>
      {[{ id: "", name: "none" }, ...characters].map((c) => (
        <button
          key={c.id || "none"}
          onClick={() => setCharId(c.id)}
          className={`rounded-full border px-2 py-0.5 font-mono text-[0.6rem] transition-colors ${
            charId === c.id ? "border-accent text-accent" : "border-border text-faint hover:text-fg"
          }`}
        >
          {c.name}
        </button>
      ))}
    </div>
  );

  return (
    <Panel className="rise overflow-hidden" style={{ animationDelay: `${delay}ms` }}>
      <div className={`relative ${aspectClass(aspect)} bg-bg-soft`} aria-busy={busyState}>
        {active ? (
          <video src={active.video_url!} controls className="size-full object-cover" />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 p-3 text-center">
            {busyState ? (
              <>
                <Spinner className="size-6 text-accent opacity-100" />
                <StatusBadge status={generating || jobRunning ? "running" : "queued"} />
              </>
            ) : failed ? (
              <>
                <StatusBadge status="failed" />
                <span className="px-2 text-xs text-faint">{failedReason || "Generation failed"}</span>
                {picker}
                <Button onClick={genWith}>Retry shot</Button>
              </>
            ) : mockDone ? (
              <>
                <StatusBadge status="succeeded" />
                <span className="font-mono text-[0.7rem] text-faint">rendered — preview unavailable (mock)</span>
              </>
            ) : (
              <>
                {picker}
                <Button variant="primary" onClick={genWith}>Generate shot</Button>
              </>
            )}
          </div>
        )}
        {activeModel && (
          <span className="absolute bottom-2 left-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.65rem] text-accent backdrop-blur">
            {activeModel}
          </span>
        )}
        <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.7rem] text-fg backdrop-blur">
          #{shot.order} · {model}
        </span>
        <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.7rem] text-accent backdrop-blur">
          {shot.duration_sec}s
        </span>
      </div>
      <div className="p-4">
        <p className="text-sm text-fg">{shot.purpose}</p>
        <p className="mt-1 font-mono text-[0.7rem] leading-relaxed text-faint">
          {shot.camera_spec.shot_size} · {shot.camera_spec.movement} — {shot.performance_spec.subject}:{" "}
          {shot.performance_spec.action}
        </p>
        {withVideo.length > 1 && (
          <div className="mt-3 flex items-center gap-2" role="radiogroup" aria-label="Takes">
            <span className="text-[0.7rem] text-faint">takes</span>
            {withVideo.map((v, i) => {
              const on = v.selected || v.id === active?.id;
              return (
                <button
                  key={v.id}
                  onClick={() => onPick(v.id)}
                  role="radio"
                  aria-checked={on}
                  aria-label={`Take ${i + 1}`}
                  className={`grid size-9 place-items-center rounded-full font-mono text-[0.6rem] transition-colors ${
                    on ? "text-accent" : "text-faint hover:text-fg"
                  }`}
                >
                  <span className={`grid size-6 place-items-center rounded-full border ${on ? "border-accent bg-accent/20" : "border-border"}`}>
                    {i + 1}
                  </span>
                </button>
              );
            })}
            {!busyState && (
              <button onClick={genWith} className="ml-auto px-2 py-1.5 font-mono text-[0.7rem] text-faint hover:text-accent">
                + retake
              </button>
            )}
          </div>
        )}
        {active && !busyState && (
          <div className="mt-3 border-t border-border pt-3">
            {showEdit ? (
              <div className="flex items-center gap-2">
                <input
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && editText.trim()) {
                      onEdit(active.id, editText);
                      setEditText("");
                      setShowEdit(false);
                    }
                  }}
                  autoFocus
                  placeholder="change the background to night…"
                  className="min-w-0 flex-1 rounded border border-border bg-bg-soft px-2 py-1 font-mono text-[0.7rem] text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent"
                />
                <button
                  onClick={() => {
                    if (editText.trim()) {
                      onEdit(active.id, editText);
                      setEditText("");
                      setShowEdit(false);
                    }
                  }}
                  className="shrink-0 font-mono text-[0.7rem] text-accent hover:underline"
                >
                  apply
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowEdit(true)}
                className="font-mono text-[0.7rem] text-faint transition-colors hover:text-accent"
              >
                ✎ edit this take · videoedit
              </button>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

function ConceptSetCard({
  cs,
  aspect,
  busy,
  onGenerate,
  onPromote,
  delay,
}: {
  cs: ConceptSet;
  aspect: string;
  busy: boolean;
  onGenerate: () => void;
  onPromote: (frameId: string, target: string) => void;
  delay: number;
}) {
  const hasImages = cs.look_frames.some((f) => isPlayable(f.image_url));
  const triedButNoPreview = !hasImages && cs.status === "generated";
  return (
    <Panel className="rise p-4" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Eyebrow>Scene {cs.scene_order} · {cs.type}</Eyebrow>
          <StatusBadge status={cs.status} />
        </div>
        {!hasImages && <Button onClick={onGenerate} loading={busy}>Generate images</Button>}
      </div>
      <p className="mt-2 text-sm text-muted">{cs.brief}</p>
      {triedButNoPreview && (
        <p className="mt-1 font-mono text-[0.7rem] text-faint">No previews available (mock mode)</p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cs.look_frames.map((f, i) => (
          <div key={f.id} className={`group relative ${aspectClass(aspect)} overflow-hidden rounded-[var(--radius)] border border-border bg-bg-soft`}>
            {isPlayable(f.image_url) ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={f.image_url!} alt={`Concept frame ${i + 1}`} title={f.prompt} className="size-full object-cover" />
            ) : busy ? (
              <div className="size-full shimmer" />
            ) : (
              <div className="flex size-full items-center justify-center p-2 text-center font-mono text-[0.6rem] text-faint">
                {f.prompt.slice(0, 60)}
              </div>
            )}
            {isPlayable(f.image_url) && (
              <div
                className={`absolute inset-x-0 bottom-0 flex font-mono text-[0.6rem] backdrop-blur transition-opacity ${
                  f.promoted_as === "none"
                    ? "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
                    : "opacity-100"
                }`}
              >
                <button
                  onClick={() => onPromote(f.id, "first_frame")}
                  aria-label="Set as first frame"
                  aria-pressed={f.promoted_as === "first_frame"}
                  className={`flex-1 py-2 ${f.promoted_as === "first_frame" ? "bg-accent/80 text-bg" : "bg-black/60 text-fg hover:bg-black/80"}`}
                >
                  {f.promoted_as === "first_frame" ? "★ frame" : "frame"}
                </button>
                <button
                  onClick={() => onPromote(f.id, "character_ref")}
                  aria-label="Cast as character"
                  aria-pressed={f.promoted_as === "character_ref"}
                  className={`flex-1 border-l border-bg/40 py-2 ${f.promoted_as === "character_ref" ? "bg-accent/80 text-bg" : "bg-black/60 text-fg hover:bg-black/80"}`}
                >
                  {f.promoted_as === "character_ref" ? "★ cast" : "cast"}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
