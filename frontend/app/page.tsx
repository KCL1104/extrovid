"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createProject, deleteProject, listProjects, type Project } from "@/lib/api";
import { Alert, Button, Eyebrow, Panel, Pill, StatusBadge } from "@/components/ui";
import Shell from "@/components/Shell";
import { PROJECTS_CHANGED } from "@/components/Sidebar";
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
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const router = useRouter();

  async function load() {
    try {
      setProjects(await listProjects());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
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
    setConfirmId(null);
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
          {projects === null ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[0, 1].map((i) => (
                <div key={i} className="h-24 rounded-[var(--radius)] shimmer" />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <p className="mt-4 text-faint">No projects yet — create one above.</p>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {projects.map((p, i) => (
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
                      {confirmId === p.id ? (
                        <span className="flex shrink-0 items-center gap-1.5 font-mono text-xs">
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              remove(p.id);
                            }}
                            className="rounded px-1.5 py-0.5 text-fail hover:bg-fail/10"
                          >
                            delete
                          </button>
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              setConfirmId(null);
                            }}
                            className="rounded px-1.5 py-0.5 text-faint hover:text-fg"
                          >
                            cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            setConfirmId(p.id);
                          }}
                          aria-label={`Delete ${p.title}`}
                          className="-m-2 shrink-0 p-2 text-faint transition-opacity hover:text-fail [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      <StatusBadge status={p.status} />
                      <Pill>{p.aspect_ratio}</Pill>
                      <Pill>{p.target_duration_sec}s</Pill>
                    </div>
                  </Panel>
                </Link>
              ))}
            </div>
          )}
        </section>
      </main>
    </Shell>
  );
}
