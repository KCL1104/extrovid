"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createProject, deleteProject, listProjects, type Project } from "@/lib/api";
import { Alert, Button, Eyebrow, Panel, Pill, ScoreBadge, StatusBadge, cn } from "@/components/ui";
import Shell from "@/components/Shell";
import { PROJECTS_CHANGED } from "@/components/Sidebar";
import { relTime } from "@/components/workspace/shared";
import UsageBadge from "@/components/UsageBadge";

const ASPECTS = ["9:16", "16:9", "1:1", "4:5"];
const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";
const field =
  "mt-1 w-full rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-fg outline-none placeholder:text-faint focus:border-accent/60";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [aspect, setAspect] = useState("9:16");
  const [duration, setDuration] = useState(20);
  const [creating, setCreating] = useState(false);
  const [confirmProject, setConfirmProject] = useState<Project | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const router = useRouter();

  const statuses = projects ? [...new Set(projects.map((p) => p.status))] : [];
  const filtered =
    projects?.filter((p) => statusFilter === "all" || p.status === statusFilter) ?? null;

  const load = () =>
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      const p = await createProject({
        title: title.trim() || undefined,
        aspect_ratio: aspect,
        target_duration_sec: duration,
      });
      window.dispatchEvent(new Event(PROJECTS_CHANGED));
      router.push(`/projects/${p.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setCreating(false);
    }
  }

  async function remove(id: string) {
    setConfirmProject(null);
    setConfirmText("");
    setProjects((p) => p?.filter((x) => x.id !== id) ?? null);
    try {
      await deleteProject(id);
      window.dispatchEvent(new Event(PROJECTS_CHANGED));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete project — please try again.");
      load();
    }
  }

  return (
    <Shell>
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-16 lg:px-8">
        <header className="rise">
          <div className="flex items-center justify-between gap-3">
            <Eyebrow>AI-native director · brief → rough cut</Eyebrow>
            <UsageBadge />
          </div>
          <h1 className="title mt-3 text-4xl text-fg sm:text-5xl lg:text-6xl">
            start a new <span className="italic text-accent">project</span>
          </h1>
          <p className="mt-4 max-w-xl leading-relaxed text-muted">
            Define the intent. The system writes the script, previsualizes the look, generates each
            shot, and assembles the cut.
          </p>
          <div className="mt-8 h-px w-full bg-gradient-to-r from-accent/50 via-border to-transparent" />
        </header>

        <Panel className="rise mt-10 p-5">
          <Eyebrow>New project</Eyebrow>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex-1">
              <span className="text-xs text-faint">Title (optional)</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !creating) create();
                }}
                disabled={creating}
                placeholder="We'll name it Project N if left blank"
                className={`${field} ${focusRing}`}
              />
            </label>
            <label>
              <span className="text-xs text-faint">Aspect</span>
              <select
                value={aspect}
                onChange={(e) => setAspect(e.target.value)}
                className={`${field} font-mono text-sm sm:w-24 ${focusRing}`}
              >
                {ASPECTS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="text-xs text-faint">Seconds</span>
              <input
                type="number"
                min={5}
                max={120}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                className={`${field} font-mono text-sm sm:w-24 ${focusRing}`}
              />
            </label>
            <Button variant="primary" onClick={create} loading={creating}>
              Create & open
            </Button>
          </div>
        </Panel>

        {error && (
          <div className="mt-4">
            <Alert>{error}</Alert>
          </div>
        )}

        <section className="mt-10">
          <Eyebrow>Projects {projects ? `· ${projects.length}` : ""}</Eyebrow>
          {projects && projects.length > 0 && statuses.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {["all", ...statuses].map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  aria-pressed={statusFilter === s}
                  className={cn(
                    "min-h-8 rounded-full border px-2.5 font-mono text-[0.65rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                    statusFilter === s
                      ? "border-accent text-accent"
                      : "border-border text-faint hover:text-fg",
                  )}
                >
                  {s}
                  {s !== "all" ? ` · ${projects.filter((p) => p.status === s).length}` : ""}
                </button>
              ))}
            </div>
          )}
          {projects === null ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[0, 1].map((i) => (
                <div key={i} className="h-24 rounded-[var(--radius)] shimmer" />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <p className="mt-4 text-faint">No projects yet — create one above.</p>
          ) : filtered && filtered.length === 0 ? (
            <p className="mt-4 text-faint">No {statusFilter} projects.</p>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {(filtered ?? []).map((p, i) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="group rise block"
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  <Panel className="p-5 transition-colors hover:border-accent/40 hover:bg-panel-hi">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="title min-w-0 flex-1 truncate text-2xl text-fg transition-colors group-hover:text-accent">
                        {p.title}
                      </h3>
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          setConfirmText("");
                          setConfirmProject(p);
                        }}
                        aria-label={`Delete ${p.title}`}
                        className="-m-2 shrink-0 p-2 text-faint transition-opacity hover:text-fail [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
                      >
                        ✕
                      </button>
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <StatusBadge status={p.status} />
                      <Pill>{p.aspect_ratio}</Pill>
                      <Pill>{p.target_duration_sec}s</Pill>
                      {p.stats?.avg_score != null && <ScoreBadge score={p.stats.avg_score} />}
                      <span className="ml-auto font-mono text-[0.6rem] text-faint">
                        {relTime(p.created_at)}
                      </span>
                    </div>
                    {p.stats && p.stats.shots > 0 && (
                      <div className="mt-3 border-t border-border pt-3">
                        <div className="flex items-center justify-between font-mono text-[0.65rem] text-faint">
                          <span>
                            {p.stats.rendered_shots}/{p.stats.shots} shots rendered
                          </span>
                          <span>
                            {p.stats.scenes} scenes
                            {p.stats.cuts > 0 ? ` · ${p.stats.cuts} cut${p.stats.cuts > 1 ? "s" : ""}` : ""}
                          </span>
                        </div>
                        <div
                          className="mt-1.5 h-1 overflow-hidden rounded-full bg-bg-soft"
                          role="progressbar"
                          aria-label="Shots rendered"
                          aria-valuemin={0}
                          aria-valuemax={p.stats.shots}
                          aria-valuenow={p.stats.rendered_shots}
                        >
                          <div
                            className="h-full rounded-full bg-accent/70 transition-all"
                            style={{
                              width: `${Math.round((p.stats.rendered_shots / Math.max(1, p.stats.shots)) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                  </Panel>
                </Link>
              ))}
            </div>
          )}
        </section>

        {confirmProject && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            onClick={() => setConfirmProject(null)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md rounded-[var(--radius)] border border-fail/30 bg-panel p-6 shadow-2xl"
            >
              <h2 className="title text-xl text-fg">Delete this project?</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                This permanently deletes{" "}
                <span className="text-fg">“{confirmProject.title}”</span> — its scenes, shots,
                generated images and videos, and any cut. This can’t be undone.
              </p>
              <label className="mt-4 block">
                <span className="text-xs text-faint">
                  Type <span className="font-mono text-fg">{confirmProject.title}</span> to confirm
                </span>
                <input
                  autoFocus
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setConfirmProject(null);
                    if (e.key === "Enter" && confirmText.trim() === confirmProject.title.trim())
                      remove(confirmProject.id);
                  }}
                  placeholder={confirmProject.title}
                  className={`${field} ${focusRing}`}
                />
              </label>
              <div className="mt-5 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setConfirmProject(null)}>
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  disabled={confirmText.trim() !== confirmProject.title.trim()}
                  onClick={() => remove(confirmProject.id)}
                >
                  Delete project
                </Button>
              </div>
            </div>
          </div>
        )}
      </main>
    </Shell>
  );
}
