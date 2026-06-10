"use client";

import { useRef, useState } from "react";
import {
  Clapperboard,
  FileText,
  Palette,
  PenLine,
  type LucideIcon,
} from "lucide-react";
import {
  clarifyBrief,
  runBrief,
  runScript,
  runStoryboard,
  runVisualBriefs,
  type ClarifyAnswer,
  type ClarifyQuestion,
  type ClarifyResult,
  type ConceptSet,
  type Scene,
} from "@/lib/api";
import { Button, Eyebrow, Panel, Pill, Spinner, cn } from "@/components/ui";
import { errMsg } from "@/components/workspace/shared";

const EXAMPLE_BRIEFS = [
  "A 20s vertical teaser for a specialty coffee brand — warm, energetic, ends on the logo.",
  "A 15s moody product reveal for a minimalist watch — slow push-in on the dial.",
];

type StageStatus = "idle" | "running" | "done" | "error";
type Stage = { id: string; label: string; icon: LucideIcon; status: StageStatus; detail?: string };

const FRESH_STAGES: Stage[] = [
  { id: "brief", label: "Parse brief", icon: FileText, status: "idle" },
  { id: "script", label: "Write script", icon: PenLine, status: "idle" },
  { id: "looks", label: "Develop looks", icon: Palette, status: "idle" },
  { id: "board", label: "Break down shots", icon: Clapperboard, status: "idle" },
];

export default function PlanPanel({
  projectId,
  planned,
  scenes,
  conceptSets,
  onPlanned,
}: {
  projectId: string;
  planned: boolean;
  scenes: Scene[];
  conceptSets: ConceptSet[];
  onPlanned: () => Promise<void>;
}) {
  const [brief, setBrief] = useState("");
  const [stages, setStages] = useState<Stage[]>(FRESH_STAGES);
  const [running, setRunning] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // director Q&A (clarifying questions before the staged run)
  const [checking, setChecking] = useState(false);
  const [assessment, setAssessment] = useState<string | null>(null);
  const [questions, setQuestions] = useState<ClarifyQuestion[]>([]);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [custom, setCustom] = useState<Record<string, string>>({});
  const lastAnswers = useRef<ClarifyAnswer[]>([]);

  const mark = (id: string, status: StageStatus, detail?: string) =>
    setStages((s) => s.map((st) => (st.id === id ? { ...st, status, detail } : st)));

  async function run(clarifications: ClarifyAnswer[]) {
    if (running) return;
    lastAnswers.current = clarifications;
    setConfirmReplace(false);
    setRunning(true);
    setError(null);
    setStages(FRESH_STAGES.map((s) => ({ ...s })));
    let current = "brief";
    try {
      mark("brief", "running");
      const b = await runBrief(projectId, brief.trim(), clarifications);
      mark("brief", "done", `${b.target_duration_sec}s · ${b.aspect_ratio} · ${b.platform}`);

      current = "script";
      mark("script", "running");
      const script = await runScript(projectId, b);
      mark("script", "done", `${script.scenes.length} scenes — “${script.logline}”`);

      current = "looks";
      mark("looks", "running");
      const plans = await runVisualBriefs(projectId, script);
      mark("looks", "done", `${plans.concept_specs.length} concept sets planned`);

      current = "board";
      mark("board", "running");
      await runStoryboard(projectId, script, plans.concept_specs, b.target_duration_sec);
      mark("board", "done", "shot list ready");

      await onPlanned();
    } catch (e) {
      mark(current, "error");
      setError(errMsg(e));
    } finally {
      setRunning(false);
    }
  }

  /** Ask the director's assistant whether the brief needs clarifying before planning. */
  async function begin() {
    if (!brief.trim() || running || checking) return;
    setConfirmReplace(false);
    setChecking(true);
    setError(null);
    setQuestions([]);
    setPicked({});
    setCustom({});
    setAssessment(null);
    let result: ClarifyResult | null = null;
    try {
      result = await clarifyBrief(projectId, brief.trim());
    } catch {
      // the clarify pass is advisory — fall through and plan directly
    }
    setChecking(false);
    if (result?.prompt_assessment) setAssessment(result.prompt_assessment);
    if (result?.needs_clarification && result.questions.length > 0) {
      setQuestions(result.questions);
      return; // wait for the user to answer or skip
    }
    await run([]);
  }

  function start() {
    if (!brief.trim() || running || checking) return;
    if (planned) setConfirmReplace(true);
    else begin();
  }

  const answerFor = (q: ClarifyQuestion) => (picked[q.id] ?? custom[q.id] ?? "").trim();
  const answered = questions.filter((q) => answerFor(q)).length;

  const collectAnswers = (): ClarifyAnswer[] =>
    questions
      .map((q) => ({ question_id: q.id, question: q.question, answer: answerFor(q) }))
      .filter((a) => a.answer.length > 0);

  function pickOption(qid: string, option: string) {
    setPicked((p) => {
      const next = { ...p };
      if (next[qid] === option) delete next[qid]; // toggle off → unanswered
      else next[qid] = option;
      return next;
    });
    setCustom((c) => ({ ...c, [qid]: "" }));
  }

  function typeCustom(qid: string, value: string) {
    setCustom((c) => ({ ...c, [qid]: value }));
    setPicked((p) => {
      if (!(qid in p)) return p;
      const next = { ...p };
      delete next[qid];
      return next;
    });
  }

  function continueRun() {
    const answers = collectAnswers();
    setQuestions([]);
    void run(answers);
  }

  function skipQuestions() {
    setQuestions([]);
    void run([]);
  }

  const anyStage = stages.some((s) => s.status !== "idle");

  return (
    <div className="space-y-6">
      {/* brief */}
      <Panel className="rise p-5">
        <Eyebrow>{planned ? "Re-brief" : "Brief"}</Eyebrow>
        <label className="sr-only" htmlFor="brief-input">
          Creative brief
        </label>
        <textarea
          id="brief-input"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder={EXAMPLE_BRIEFS[0]}
          rows={3}
          className="mt-3 w-full resize-none rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        />
        {confirmReplace ? (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-sm text-fail">
              Re-planning replaces the current script, looks, storyboard, and generated takes.
            </span>
            <Button variant="danger" onClick={begin}>
              Replace plan
            </Button>
            <Button variant="ghost" onClick={() => setConfirmReplace(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              onClick={start}
              loading={running || checking}
              disabled={!brief.trim()}
            >
              {planned ? "Re-plan production" : "Plan production"}
            </Button>
            {checking ? (
              <span className="text-xs text-faint">Checking your brief for open questions…</span>
            ) : (
              !running && (
                <span className="text-xs text-faint">
                  Brief → script → look development → storyboard, staged below as it runs.
                </span>
              )
            )}
          </div>
        )}
        {assessment && (
          <p className="mt-3 border-t border-border pt-2.5 font-mono text-xs text-faint">
            {assessment}
          </p>
        )}
        {!planned && !brief.trim() && !anyStage && (
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

      {/* director Q&A — inline clarifying questions before the staged run */}
      {questions.length > 0 && (
        <Panel className="rise p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Eyebrow>Director Q&amp;A</Eyebrow>
            <span className="font-mono text-[0.7rem] text-faint">
              {answered}/{questions.length} answered
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            Optional — answer what helps, leave the rest blank. Your answers steer the whole plan.
          </p>
          <div className="mt-4 space-y-3">
            {questions.map((q) => (
              <div key={q.id} className="rounded-[var(--radius)] border border-border p-3">
                <p className="text-sm text-fg">{q.question}</p>
                <p className="mt-0.5 text-xs text-faint">{q.why}</p>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {q.options.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => pickOption(q.id, opt)}
                      aria-pressed={picked[q.id] === opt}
                      className={cn(
                        "min-h-9 rounded-full border px-3 font-mono text-[0.7rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                        picked[q.id] === opt
                          ? "border-accent bg-accent/10 text-accent"
                          : "border-border text-muted hover:border-accent/40 hover:text-fg",
                      )}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
                {q.allow_custom && (
                  <>
                    <label className="sr-only" htmlFor={`clarify-${q.id}`}>
                      Custom answer
                    </label>
                    <input
                      id={`clarify-${q.id}`}
                      value={custom[q.id] ?? ""}
                      onChange={(e) => typeCustom(q.id, e.target.value)}
                      placeholder="or write your own…"
                      className="mt-2 w-full rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 font-mono text-xs text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    />
                  </>
                )}
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button variant="primary" onClick={continueRun}>
              {answered
                ? `Continue with ${answered} answer${answered === 1 ? "" : "s"}`
                : "Continue"}
            </Button>
            <Button variant="ghost" onClick={skipQuestions}>
              Skip questions
            </Button>
          </div>
        </Panel>
      )}

      {/* staged run console */}
      {anyStage && (
        <Panel className="rise p-5">
          <Eyebrow>AI planning</Eyebrow>
          <ol className="mt-3 space-y-2.5">
            {stages.map((s) => {
              const Icon = s.icon;
              return (
                <li key={s.id} className="flex items-start gap-3">
                  <span
                    className={cn(
                      "mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border",
                      s.status === "done" && "border-ok/50 text-ok",
                      s.status === "running" && "border-accent/50 text-accent",
                      s.status === "error" && "border-fail/50 text-fail",
                      s.status === "idle" && "border-border text-faint",
                    )}
                  >
                    {s.status === "running" ? (
                      <Spinner className="size-3.5" />
                    ) : (
                      <Icon size={13} aria-hidden />
                    )}
                  </span>
                  <div className="min-w-0">
                    <p
                      className={cn(
                        "font-mono text-xs",
                        s.status === "idle" ? "text-faint" : "text-fg",
                      )}
                    >
                      {s.label}
                      {s.status === "done" && <span className="ml-2 text-ok">✓</span>}
                      {s.status === "error" && <span className="ml-2 text-fail">failed</span>}
                    </p>
                    {s.detail && <p className="mt-0.5 text-xs text-muted">{s.detail}</p>}
                  </div>
                </li>
              );
            })}
          </ol>
          {error && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="font-mono text-xs text-fail">{error}</span>
              <Button onClick={() => run(lastAnswers.current)} loading={running}>
                Retry
              </Button>
            </div>
          )}
        </Panel>
      )}

      {/* script */}
      {scenes.length > 0 && (
        <section>
          <Eyebrow>Script · {scenes.length} scenes</Eyebrow>
          <div className="mt-4 space-y-4">
            {scenes.map((scene, i) => {
              const vb = conceptSets.find((c) => c.scene_order === scene.order)?.visual_brief;
              return (
                <Panel key={scene.id} className="rise p-5" style={{ animationDelay: `${i * 50}ms` }}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-display text-xl text-fg">
                      <span className="mr-2 font-mono text-xs text-accent">
                        S{scene.order + 1}
                      </span>
                      {scene.title}
                    </h3>
                    <Pill>{scene.est_duration_sec.toFixed(0)}s</Pill>
                  </div>
                  <p className="mt-1 text-sm text-muted">{scene.summary}</p>
                  <ul className="mt-3 space-y-1.5">
                    {scene.beats.map((b) => (
                      <li key={b.order} className="flex gap-2 text-sm">
                        <span className="font-mono text-[0.7rem] text-faint">{b.order + 1}</span>
                        <span className="min-w-0">
                          <span className="text-fg">{b.description}</span>
                          {(b.narration || b.dialogue) && (
                            <span className="mt-0.5 block font-mono text-[0.7rem] text-accent/80">
                              {b.dialogue ? `“${b.dialogue}”` : b.narration}
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {vb && (
                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                      <span className="font-mono text-[0.65rem] uppercase tracking-widest text-faint">
                        direction
                      </span>
                      <Pill>{vb.visual_style}</Pill>
                      <Pill>{vb.mood}</Pill>
                      <Pill>{vb.lighting}</Pill>
                      <span className="ml-1 inline-flex items-center gap-1" title="Palette">
                        {vb.palette.slice(0, 4).map((c) => (
                          <span
                            key={c}
                            aria-hidden
                            className="size-3 rounded-full border border-border-hi"
                            // palette swatches come from the AI visual brief, not the theme
                            style={{ backgroundColor: c }}
                          />
                        ))}
                      </span>
                    </div>
                  )}
                </Panel>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
