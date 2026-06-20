"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Lock,
  LockOpen,
  MessageSquarePlus,
  Wand2,
} from "lucide-react";
import {
  applyRevision,
  approvePlan,
  createAnnotation,
  getOutline,
  getPlanCost,
  getProjectState,
  listAnnotations,
  lockScene,
  lockShot,
  proposeRevision,
  resolveAnnotation,
  type Act,
  type Annotation,
  type PlanCost,
  type ProjectState,
  type ReviseProposal,
  type Scene,
  type Shot,
} from "@/lib/api";
import { Button, Eyebrow, Panel, Pill, cn } from "@/components/ui";
import { errMsg } from "@/components/workspace/shared";

type Target = { kind: "scene" | "shot"; id: string };

/** Top-level fields that differ between the current value and a proposed revision. */
function changedFields(before: Record<string, unknown>, after: Record<string, unknown>) {
  const keys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]);
  const fmt = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
  return [...keys]
    .filter((k) => JSON.stringify(before?.[k]) !== JSON.stringify(after?.[k]))
    .map((k) => ({ key: k, before: fmt(before?.[k]), after: fmt(after?.[k]) }));
}

export default function ReviewPanel({
  projectId,
  scenes,
  shots,
  onRefresh,
}: {
  projectId: string;
  scenes: Scene[];
  shots: Shot[];
  onRefresh: () => Promise<void> | void;
}) {
  const [state, setState] = useState<ProjectState | null>(null);
  const [cost, setCost] = useState<PlanCost | null>(null);
  const [acts, setActs] = useState<Act[]>([]);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [budget, setBudget] = useState(""); // empty -> defaults to the projected cost

  // inline composers (one open at a time), keyed by `${kind}:${id}`
  const [noteFor, setNoteFor] = useState<Target | null>(null);
  const [noteText, setNoteText] = useState("");
  const [reviseFor, setReviseFor] = useState<Target | null>(null);
  const [reviseText, setReviseText] = useState("");
  const [proposal, setProposal] = useState<ReviseProposal | null>(null);

  const loadGate = useCallback(async () => {
    const [s, c, a, ac] = await Promise.all([
      getProjectState(projectId),
      getPlanCost(projectId),
      listAnnotations(projectId),
      getOutline(projectId),
    ]);
    setState(s);
    setCost(c);
    setAnnotations(a);
    setActs(ac);
  }, [projectId]);

  useEffect(() => {
    // microtask defer keeps the effect body free of synchronous state updates
    void Promise.resolve().then(() => loadGate().catch((e) => setError(errMsg(e))));
  }, [loadGate]);

  const refresh = useCallback(async () => {
    await Promise.all([loadGate(), onRefresh()]);
  }, [loadGate, onRefresh]);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(null);
    }
  }

  async function saveNote(t: Target) {
    if (!noteText.trim()) return;
    await act(`note:${t.id}`, () =>
      createAnnotation(projectId, {
        target_kind: t.kind,
        target_id: t.id,
        intent: "comment",
        text: noteText.trim(),
      }),
    );
    setNoteFor(null);
    setNoteText("");
  }

  async function preview(t: Target) {
    if (!reviseText.trim()) return;
    setBusy(`preview:${t.id}`);
    setError(null);
    try {
      setProposal(await proposeRevision(projectId, `${t.kind}:${t.id}`, reviseText.trim()));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(null);
    }
  }

  async function acceptProposal(t: Target) {
    if (!proposal) return;
    await act(`apply:${t.id}`, () => applyRevision(projectId, `${t.kind}:${t.id}`, proposal.after));
    setReviseFor(null);
    setReviseText("");
    setProposal(null);
  }

  async function approveWithBudget() {
    const parsed = parseFloat(budget);
    const budget_usd = Number.isFinite(parsed) && parsed > 0 ? parsed : cost?.total_usd;
    await act("approve-all", () =>
      approvePlan(projectId, budget_usd != null ? { budget_usd } : {}),
    );
  }

  const gated = !!state?.gated;
  const approved = state?.project_status === "approved";
  const tier = state?.tier ?? "—";
  // shown in the budget field: the user's typed value, else the saved budget, else projected
  const budgetVal =
    budget !== ""
      ? budget
      : state?.budget_usd != null
        ? String(state.budget_usd)
        : cost
          ? cost.total_usd.toFixed(2)
          : "";
  const actualSec = shots.reduce((n, s) => n + (s.duration_sec ?? 0), 0);
  const openNotes = annotations.filter((a) => a.status === "open");
  const notesByTarget = (id: string) => openNotes.filter((a) => a.target_id === id);

  return (
    <div className="space-y-6">
      {/* ── approval header ─────────────────────────────────────────── */}
      <Panel className="rise p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Eyebrow>Plan review</Eyebrow>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Pill className={cn(gated ? "text-accent" : "text-ok")}>{tier} tier</Pill>
              {gated ? (
                approved ? (
                  <Pill className="text-ok">approved ✓</Pill>
                ) : (
                  <Pill className="text-run">awaiting approval</Pill>
                )
              ) : (
                <Pill className="text-ok">no approval needed</Pill>
              )}
              <Pill>{scenes.length} scenes</Pill>
              <Pill>{shots.length} shots</Pill>
              <Pill>
                ~{Math.round(actualSec)}s / {state?.target_duration_sec ?? "—"}s target
              </Pill>
            </div>
            <p className="mt-3 max-w-xl text-xs leading-relaxed text-faint">
              {gated
                ? approved
                  ? "Approved. Head to the Storyboard tab to render — generation is unlocked."
                  : "Review the plan below, annotate or revise anything, then approve. Generation stays locked until you sign off — so you never spend on a wrong cut."
                : "Short videos skip the gate — you can render straight from the Storyboard tab. Annotate or revise here if you want."}
            </p>
          </div>

          {/* cost + budget + approve */}
          <div className="flex flex-col items-end gap-2">
            {cost && (
              <div className="text-right">
                <p className="font-display text-2xl text-fg">${cost.total_usd.toFixed(2)}</p>
                <p className="font-mono text-[0.65rem] text-faint">
                  est. render · vid ${cost.video_usd.toFixed(2)} · img ${cost.image_usd.toFixed(2)}
                  {cost.tts_usd > 0 ? ` · vo $${cost.tts_usd.toFixed(2)}` : ""}
                </p>
              </div>
            )}
            {state?.over_budget && (
              <p className="font-mono text-[0.65rem] text-fail">
                over budget — raise it or trim the plan
              </p>
            )}
            {gated && !approved && (
              <div className="flex items-center gap-2">
                <label className="font-mono text-[0.65rem] text-faint" htmlFor="budget">
                  budget $
                </label>
                <input
                  id="budget"
                  inputMode="decimal"
                  value={budgetVal}
                  onChange={(e) => setBudget(e.target.value)}
                  className="w-20 rounded-[var(--radius)] border border-border bg-bg-soft px-2 py-1.5 text-right font-mono text-xs text-fg outline-none focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                />
                <Button variant="primary" loading={busy === "approve-all"} onClick={approveWithBudget}>
                  <Check size={14} aria-hidden /> Approve
                </Button>
              </div>
            )}
            {approved && state?.budget_usd != null && (
              <Pill className="text-ok">budget ${state.budget_usd.toFixed(2)}</Pill>
            )}
          </div>
        </div>
        {error && <p className="mt-3 font-mono text-xs text-fail">{error}</p>}
      </Panel>

      {/* ── scene-by-scene review (progressive disclosure) ──────────── */}
      <section className="space-y-3">
        {scenes.map((scene, idx) => {
          const sceneShots = shots
            .filter((s) => s.scene_order === scene.order)
            .sort((a, b) => a.order - b.order);
          const open = expanded[scene.order] ?? false;
          const sceneTarget: Target = { kind: "scene", id: scene.id };
          // a chapter header before the first scene of each act (LONG tier)
          const aid = scene.act_id ?? null;
          const prevAid = idx > 0 ? (scenes[idx - 1].act_id ?? null) : " ";
          const chapter = acts.find((a) => a.id === aid);
          const showAct = acts.length > 0 && !!chapter && aid !== prevAid;
          return (
            <Fragment key={scene.id}>
              {showAct && chapter && (
                <div className="flex flex-wrap items-baseline gap-2 px-1 pb-1 pt-3">
                  <span className="font-mono text-xs text-accent">Act {chapter.order + 1}</span>
                  <span className="font-display text-base text-fg">{chapter.title}</span>
                  <span className="min-w-0 truncate text-xs text-faint" title={chapter.open_loop}>
                    {chapter.hook}
                  </span>
                </div>
              )}
              <Panel className="overflow-hidden">
              {/* scene header */}
              <div className="flex flex-wrap items-center justify-between gap-2 p-4">
                <button
                  onClick={() => setExpanded((e) => ({ ...e, [scene.order]: !open }))}
                  aria-expanded={open}
                  className="flex min-w-0 items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-[var(--radius)]"
                >
                  {open ? (
                    <ChevronDown size={15} className="shrink-0 text-faint" aria-hidden />
                  ) : (
                    <ChevronRight size={15} className="shrink-0 text-faint" aria-hidden />
                  )}
                  <span className="font-mono text-xs text-accent">S{scene.order + 1}</span>
                  <span className="truncate font-display text-lg text-fg">{scene.title}</span>
                  <span className="shrink-0 font-mono text-[0.65rem] text-faint">
                    {sceneShots.length} shots
                  </span>
                </button>
                <div className="flex shrink-0 items-center gap-1.5">
                  {scene.approved && <Pill className="text-ok">approved</Pill>}
                  {scene.locked && (
                    <Pill className="text-accent">
                      <Lock size={10} className="mr-1" aria-hidden /> locked
                    </Pill>
                  )}
                  {notesByTarget(scene.id).length > 0 && (
                    <Pill className="text-run">{notesByTarget(scene.id).length} ✎</Pill>
                  )}
                  {gated && !scene.approved && (
                    <Button
                      variant="ghost"
                      className="px-2"
                      loading={busy === `appr:${scene.id}`}
                      onClick={() =>
                        act(`appr:${scene.id}`, () => approvePlan(projectId, { scene_ids: [scene.id] }))
                      }
                    >
                      <Check size={13} aria-hidden /> approve
                    </Button>
                  )}
                  <button
                    title={scene.locked ? "Unlock scene" : "Lock scene (blocks revise)"}
                    onClick={() => act(`lock:${scene.id}`, () => lockScene(projectId, scene.id, !scene.locked))}
                    className="inline-flex min-h-9 items-center rounded-[var(--radius)] px-2 text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    {scene.locked ? <LockOpen size={14} aria-hidden /> : <Lock size={14} aria-hidden />}
                  </button>
                  <button
                    title="Add a note"
                    onClick={() => {
                      setNoteFor(noteFor?.id === scene.id ? null : sceneTarget);
                      setNoteText("");
                    }}
                    className="inline-flex min-h-9 items-center rounded-[var(--radius)] px-2 text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <MessageSquarePlus size={14} aria-hidden />
                  </button>
                  <button
                    title="Revise this scene (preview the change before applying)"
                    onClick={() => {
                      setReviseFor(reviseFor?.id === scene.id ? null : sceneTarget);
                      setReviseText("");
                      setProposal(null);
                    }}
                    disabled={scene.locked}
                    className="inline-flex min-h-9 items-center rounded-[var(--radius)] px-2 text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-30"
                  >
                    <Wand2 size={14} aria-hidden />
                  </button>
                </div>
              </div>

              {/* note composer */}
              {noteFor?.id === scene.id && (
                <NoteComposer
                  value={noteText}
                  onChange={setNoteText}
                  busy={busy === `note:${scene.id}`}
                  onSave={() => saveNote(sceneTarget)}
                />
              )}
              {/* revise composer + diff */}
              {reviseFor?.id === scene.id && (
                <ReviseComposer
                  value={reviseText}
                  onChange={(v) => {
                    setReviseText(v);
                    setProposal(null);
                  }}
                  proposal={proposal}
                  previewing={busy === `preview:${scene.id}`}
                  applying={busy === `apply:${scene.id}`}
                  onPreview={() => preview(sceneTarget)}
                  onApply={() => acceptProposal(sceneTarget)}
                />
              )}

              {/* scene notes */}
              {open && notesByTarget(scene.id).length > 0 && (
                <NoteList notes={notesByTarget(scene.id)} onResolve={(a) => act(`res:${a.id}`, () => resolveAnnotation(projectId, a.id))} />
              )}

              {/* shots */}
              {open && (
                <ul className="border-t border-border">
                  {sceneShots.map((shot) => (
                    <li key={shot.id} className="border-b border-border/60 px-4 py-2.5 last:border-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="font-mono text-[0.65rem] text-faint">#{shot.order + 1}</span>
                          <span className="truncate text-sm text-fg">{shot.purpose}</span>
                          <span className="shrink-0 font-mono text-[0.65rem] text-faint">
                            {shot.duration_sec.toFixed(1)}s
                          </span>
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          {shot.locked && (
                            <Pill className="text-accent">
                              <Lock size={9} className="mr-1" aria-hidden /> locked
                            </Pill>
                          )}
                          {notesByTarget(shot.id).length > 0 && (
                            <Pill className="text-run">{notesByTarget(shot.id).length} ✎</Pill>
                          )}
                          <button
                            title={shot.locked ? "Unlock shot" : "Lock shot"}
                            onClick={() => act(`lock:${shot.id}`, () => lockShot(projectId, shot.id, !shot.locked))}
                            className="inline-flex min-h-8 items-center rounded-[var(--radius)] px-1.5 text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                          >
                            {shot.locked ? <LockOpen size={13} aria-hidden /> : <Lock size={13} aria-hidden />}
                          </button>
                          <button
                            title="Add a note"
                            onClick={() => {
                              setNoteFor(noteFor?.id === shot.id ? null : { kind: "shot", id: shot.id });
                              setNoteText("");
                            }}
                            className="inline-flex min-h-8 items-center rounded-[var(--radius)] px-1.5 text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                          >
                            <MessageSquarePlus size={13} aria-hidden />
                          </button>
                          <button
                            title="Revise this shot"
                            disabled={shot.locked}
                            onClick={() => {
                              setReviseFor(reviseFor?.id === shot.id ? null : { kind: "shot", id: shot.id });
                              setReviseText("");
                              setProposal(null);
                            }}
                            className="inline-flex min-h-8 items-center rounded-[var(--radius)] px-1.5 text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-30"
                          >
                            <Wand2 size={13} aria-hidden />
                          </button>
                        </div>
                      </div>
                      {noteFor?.id === shot.id && (
                        <NoteComposer
                          value={noteText}
                          onChange={setNoteText}
                          busy={busy === `note:${shot.id}`}
                          onSave={() => saveNote({ kind: "shot", id: shot.id })}
                        />
                      )}
                      {reviseFor?.id === shot.id && (
                        <ReviseComposer
                          value={reviseText}
                          onChange={(v) => {
                            setReviseText(v);
                            setProposal(null);
                          }}
                          proposal={proposal}
                          previewing={busy === `preview:${shot.id}`}
                          applying={busy === `apply:${shot.id}`}
                          onPreview={() => preview({ kind: "shot", id: shot.id })}
                          onApply={() => acceptProposal({ kind: "shot", id: shot.id })}
                        />
                      )}
                      {notesByTarget(shot.id).length > 0 && (
                        <NoteList
                          notes={notesByTarget(shot.id)}
                          onResolve={(a) => act(`res:${a.id}`, () => resolveAnnotation(projectId, a.id))}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              )}
              </Panel>
            </Fragment>
          );
        })}
      </section>
    </div>
  );
}

// ── small composers ───────────────────────────────────────────────

function NoteComposer({
  value,
  onChange,
  busy,
  onSave,
}: {
  value: string;
  onChange: (v: string) => void;
  busy: boolean;
  onSave: () => void;
}) {
  return (
    <div className="flex items-center gap-2 px-4 pb-3">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSave()}
        placeholder="leave a note for this element…"
        className="min-w-0 flex-1 rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 font-mono text-xs text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      />
      <Button onClick={onSave} loading={busy} disabled={!value.trim()}>
        Add note
      </Button>
    </div>
  );
}

function ReviseComposer({
  value,
  onChange,
  proposal,
  previewing,
  applying,
  onPreview,
  onApply,
}: {
  value: string;
  onChange: (v: string) => void;
  proposal: ReviseProposal | null;
  previewing: boolean;
  applying: boolean;
  onPreview: () => void;
  onApply: () => void;
}) {
  const diff = proposal ? changedFields(proposal.before, proposal.after) : [];
  return (
    <div className="px-4 pb-3">
      <div className="flex items-center gap-2">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onPreview()}
          placeholder="“make the hook moodier, end on the close-up”"
          className="min-w-0 flex-1 rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 font-mono text-xs text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        />
        <Button onClick={onPreview} loading={previewing} disabled={!value.trim()}>
          Preview
        </Button>
      </div>
      {proposal && (
        <div className="mt-2 rounded-[var(--radius)] border border-border bg-bg-soft p-3">
          <Eyebrow>Proposed change</Eyebrow>
          {diff.length === 0 ? (
            <p className="mt-2 font-mono text-xs text-faint">No changes proposed.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {diff.map((d) => (
                <li key={d.key} className="text-xs">
                  <span className="font-mono text-[0.65rem] uppercase tracking-widest text-faint">
                    {d.key}
                  </span>
                  <p className="mt-0.5 text-fail/80 line-through">{d.before || "—"}</p>
                  <p className="text-ok">{d.after || "—"}</p>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex items-center gap-2">
            <Button variant="primary" onClick={onApply} loading={applying} disabled={diff.length === 0}>
              Accept &amp; apply
            </Button>
            <Button variant="ghost" onClick={() => onChange(value)}>
              {/* re-typing clears the proposal via the parent's onChange */}
              Reject
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function NoteList({ notes, onResolve }: { notes: Annotation[]; onResolve: (a: Annotation) => void }) {
  return (
    <ul className="space-y-1.5 px-4 pb-3">
      {notes.map((a) => (
        <li
          key={a.id}
          className="flex items-start justify-between gap-2 rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2"
        >
          <span className="min-w-0 text-xs text-muted">
            {a.intent === "change" && <span className="mr-1 font-mono text-[0.6rem] text-accent">change</span>}
            {a.text}
          </span>
          <button
            onClick={() => onResolve(a)}
            className="shrink-0 font-mono text-[0.65rem] text-faint transition-colors hover:text-ok focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            resolve ✓
          </button>
        </li>
      ))}
    </ul>
  );
}
