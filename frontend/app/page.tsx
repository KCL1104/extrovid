"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createProject, listProjects, type Project } from "@/lib/api";
import { Alert, Button, Eyebrow, Panel, Pill, ScoreBadge, StatusBadge, cn } from "@/components/ui";
import Shell from "@/components/Shell";
import { PROJECTS_CHANGED } from "@/components/Sidebar";
import { relTime } from "@/components/workspace/shared";

// intent tiles pre-shape the pipeline: each picks a length tier (drives gating + planning) and,
// for "import", opens the source-import flow in the workspace.
const INTENTS = [
  { id: "short", label: "Short clip", hint: "~20s · one-prompt", seconds: 20, importMode: false },
  { id: "narrative", label: "Narrative", hint: "~60s · scenes", seconds: 60, importMode: false },
  { id: "long", label: "Long-form", hint: "~5m · chaptered", seconds: 300, importMode: false },
  { id: "import", label: "Import & revise", hint: "from a script", seconds: 120, importMode: true },
] as const;
type IntentId = (typeof INTENTS)[number]["id"];

const EXAMPLES = [
  "A 30s teaser for a cozy indie coffee brand — golden hour, handheld.",
  "A 60s sci-fi short: a courier races neon rain to deliver a memory.",
  "A reveal for a minimalist watch — slow, premium, macro detail.",
];

const ASPECTS = ["9:16", "16:9", "1:1", "4:5"];
const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [brief, setBrief] = useState("");
  const [intent, setIntent] = useState<IntentId>("narrative");
  const [aspect, setAspect] = useState("9:16");
  const [advanced, setAdvanced] = useState(false);
  const [creating, setCreating] = useState(false);
  const router = useRouter();

  const recent = projects?.slice(0, 2) ?? null;

  const load = () =>
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  useEffect(() => {
    load();
  }, []);

  async function direct() {
    if (creating) return;
    const chosen = INTENTS.find((i) => i.id === intent)!;
    setCreating(true);
    setError(null);
    try {
      // the chosen length is remembered (PlanPanel reads this) so the tier flows into planning
      if (typeof window !== "undefined") localStorage.setItem("extrovid:dur", String(chosen.seconds));
      const p = await createProject({
        title: brief.trim().slice(0, 50) || undefined,
        aspect_ratio: aspect,
        target_duration_sec: chosen.seconds,
      });
      // hand the brief (and import intent) to the workspace's Plan stage
      if (typeof window !== "undefined") {
        if (brief.trim()) sessionStorage.setItem(`extrovid:brief:${p.id}`, brief.trim());
        if (chosen.importMode) sessionStorage.setItem(`extrovid:import:${p.id}`, "1");
      }
      window.dispatchEvent(new Event(PROJECTS_CHANGED));
      router.push(`/projects/${p.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setCreating(false);
    }
  }

  return (
    <Shell>
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-16 lg:px-8">
        <header className="rise">
          <Eyebrow>AI-native director · brief → rough cut</Eyebrow>
          <h1 className="title mt-3 text-4xl text-fg sm:text-5xl lg:text-6xl">
            direct a film from a <span className="italic text-accent">brief</span>
          </h1>
        </header>

        {/* composer — generation-first: describe the film, pick an intent, direct it */}
        <Panel
          className="rise mt-8 border-accent/20 p-5"
          style={{ background: "radial-gradient(120% 140% at 50% -20%, #221a1066, transparent 60%)" }}
        >
          <Eyebrow>New film</Eyebrow>
          <label className="sr-only" htmlFor="brief-composer">
            Describe the film you want to direct
          </label>
          <textarea
            id="brief-composer"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) direct();
            }}
            rows={3}
            disabled={creating}
            placeholder="Describe the film you want to direct…"
            className={cn(
              "mt-3 w-full resize-none rounded-[var(--radius)] border border-border bg-bg-soft px-3.5 py-3 text-fg outline-none placeholder:text-faint focus:border-accent/60",
              focusRing,
            )}
          />

          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setBrief(ex)}
                className={cn(
                  "rounded-full border border-border-hi bg-bg-soft px-2.5 py-1 text-left font-mono text-[0.65rem] text-faint transition-colors hover:border-accent/40 hover:text-fg",
                  focusRing,
                )}
              >
                {ex.length > 44 ? `${ex.slice(0, 44)}…` : ex}
              </button>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {INTENTS.map((i) => (
              <button
                key={i.id}
                type="button"
                onClick={() => setIntent(i.id)}
                aria-pressed={intent === i.id}
                className={cn(
                  "rounded-[var(--radius)] border p-3 text-left transition-colors",
                  focusRing,
                  intent === i.id
                    ? "border-accent/60 bg-accent/10"
                    : "border-border bg-bg-soft hover:border-border-hi",
                )}
              >
                <div className={cn("text-sm", intent === i.id ? "text-accent" : "text-fg")}>
                  {i.label}
                </div>
                <div className="mt-0.5 font-mono text-[0.6rem] text-faint">{i.hint}</div>
              </button>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button variant="primary" onClick={direct} loading={creating} className="px-5">
              Direct it →
            </Button>
            <button
              type="button"
              onClick={() => setAdvanced((a) => !a)}
              className={cn("font-mono text-[0.7rem] text-faint transition-colors hover:text-fg", focusRing)}
            >
              {advanced ? "− advanced" : "+ advanced"}
            </button>
            {advanced && (
              <label className="flex items-center gap-2 font-mono text-[0.7rem] text-faint">
                aspect
                <select
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value)}
                  className={cn(
                    "rounded-[var(--radius)] border border-border bg-bg-soft px-2 py-1 text-fg",
                    focusRing,
                  )}
                >
                  {ASPECTS.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <span className="font-mono text-[0.6rem] text-faint">⌘⏎ to direct</span>
          </div>
        </Panel>

        {error && (
          <div className="mt-4">
            <Alert>{error}</Alert>
          </div>
        )}

        <section className="mt-10">
          <div className="flex items-baseline justify-between gap-3">
            <Eyebrow>Recent</Eyebrow>
            {projects && projects.length > 2 && (
              <span className="font-mono text-[0.65rem] text-faint">
                +{projects.length - 2} more in the sidebar
              </span>
            )}
          </div>
          {projects === null ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[0, 1].map((i) => (
                <div key={i} className="h-24 rounded-[var(--radius)] shimmer" />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <p className="mt-4 text-faint">No projects yet — describe one above.</p>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {(recent ?? []).map((p, i) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="group rise block"
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  <Panel hover className="p-5 hover:border-accent/40">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="title min-w-0 flex-1 truncate text-2xl text-fg transition-colors group-hover:text-accent">
                        {p.title}
                      </h3>
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
      </main>
    </Shell>
  );
}
