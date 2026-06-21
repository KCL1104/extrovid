"use client";

import { useState, type ChangeEvent, type ReactNode } from "react";
import { ArrowRightToLine, Columns2, ImagePlus, RefreshCw, Sparkles, Volume2, X } from "lucide-react";
import type { Character, Shot, ShotTransition, ShotUpdate, ShotVersion } from "@/lib/api";
import {
  Button,
  Drawer,
  Eyebrow,
  Panel,
  Pill,
  ScoreBadge,
  Spinner,
  StatusBadge,
  cn,
} from "@/components/ui";
import {
  aspectClass,
  chosenTake,
  errMsg,
  isPlayable,
  isRunning,
} from "@/components/workspace/shared";

const TRANSITIONS: ShotTransition[] = ["cut", "dissolve", "fade", "match_cut", "none"];

const inputCls =
  "w-full rounded-[var(--radius)] border border-border bg-bg-soft px-2.5 py-1.5 font-mono text-xs text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** Flat, string-typed editing copy of a shot's directable fields. */
function fromShot(s: Shot) {
  return {
    purpose: s.purpose,
    beat: s.beat,
    duration_sec: String(s.duration_sec),
    shot_size: s.camera_spec.shot_size,
    angle: s.camera_spec.angle,
    movement: s.camera_spec.movement,
    lens: s.camera_spec.lens ?? "",
    subject: s.performance_spec.subject,
    action: s.performance_spec.action,
    emotion: s.performance_spec.emotion ?? "",
    transition: s.transition,
    extra_direction: s.extra_direction ?? "",
    framing: s.framing ?? "",
    screen_direction: s.screen_direction ?? "",
    dialogue: s.dialogue ?? "",
    speaker: s.speaker ?? "",
    motion_desc: s.motion_desc ?? "",
  };
}
type Draft = ReturnType<typeof fromShot>;

export default function ShotInspector({
  shot,
  versions,
  characters,
  aspect,
  canContinue,
  busy,
  docked = false,
  onClose,
  onGenerate,
  onEdit,
  onPick,
  onReview,
  onUpdate,
  onKeyframe,
  onVoiceover,
}: {
  shot: Shot;
  versions: ShotVersion[];
  characters: Character[];
  aspect: string;
  canContinue: boolean;
  busy: boolean;
  docked?: boolean; // true: render as a persistent right pane; false: modal drawer (mobile)
  onClose: () => void;
  onGenerate: (opts?: {
    character_id?: string;
    continue_from_previous?: boolean;
    num_takes?: number;
  }) => void;
  onEdit: (versionId: string, instruction: string) => void;
  onPick: (versionId: string) => void;
  onReview: (versionId: string) => Promise<void>;
  onUpdate: (patch: ShotUpdate) => Promise<void>;
  onKeyframe: () => void;
  onVoiceover: () => void;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [charId, setCharId] = useState(shot.character_id ?? "");
  const [castSaving, setCastSaving] = useState(false);
  const [castError, setCastError] = useState<string | null>(null);
  const [renderMode, setRenderMode] = useState(shot.render_mode ?? "video");
  const [modeSaving, setModeSaving] = useState(false);
  const [note, setNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [numTakes, setNumTakes] = useState(1);
  // lower-panel section: keep the player+takes always visible, switch Review/Direction below
  const [section, setSection] = useState<"review" | "direction">(
    versions.some((v) => v.review) ? "review" : "direction",
  );
  // editable direction form (per-shot state resets via the parent's `key={shot.id}`)
  const [draft, setDraft] = useState<Draft>(() => fromShot(shot));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const finished = versions.filter((v) => v.output_asset_id);
  const fallback = chosenTake(versions);
  const active = finished.find((v) => v.id === activeId) ?? fallback;
  const compare = finished.find((v) => v.id === compareId && v.id !== active?.id);
  const jobRunning = busy || versions.some(isRunning);

  const sendNote = () => {
    if (active && note.trim()) {
      onEdit(active.id, note.trim());
      setNote("");
    }
  };

  async function rereview() {
    if (!active || reviewing) return;
    setReviewing(true);
    try {
      await onReview(active.id);
    } finally {
      setReviewing(false);
    }
  }

  const takeIndex = (v: ShotVersion) => finished.indexOf(v) + 1;

  // ── direction form helpers ────────────────────────────────────────────────

  const set =
    (k: keyof Draft) =>
    (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setDraft((d) => ({ ...d, [k]: e.target.value }));

  const trimmed = {
    purpose: draft.purpose.trim(),
    beat: draft.beat.trim(),
    shot_size: draft.shot_size.trim(),
    angle: draft.angle.trim(),
    movement: draft.movement.trim(),
    lens: draft.lens.trim(),
    subject: draft.subject.trim(),
    action: draft.action.trim(),
    emotion: draft.emotion.trim(),
    extra_direction: draft.extra_direction.trim(),
  };
  const duration = Number.parseFloat(draft.duration_sec);
  const durationValid = Number.isFinite(duration) && duration > 0 && duration <= 15;
  // required by the storyboard contract — an emptied field would otherwise be silently
  // dropped from the patch and the form would diverge from the persisted shot
  const missingRequired =
    !trimmed.purpose ||
    !trimmed.beat ||
    !trimmed.shot_size ||
    !trimmed.angle ||
    !trimmed.movement ||
    !trimmed.subject ||
    !trimmed.action;

  // only changed fields go into the PATCH (backend applies with exclude_unset)
  const patch: ShotUpdate = {};
  if (trimmed.purpose && trimmed.purpose !== shot.purpose) patch.purpose = trimmed.purpose;
  if (trimmed.beat && trimmed.beat !== shot.beat) patch.beat = trimmed.beat;
  if (durationValid && duration !== shot.duration_sec) patch.duration_sec = duration;
  if (
    trimmed.shot_size &&
    trimmed.angle &&
    trimmed.movement &&
    (trimmed.shot_size !== shot.camera_spec.shot_size ||
      trimmed.angle !== shot.camera_spec.angle ||
      trimmed.movement !== shot.camera_spec.movement ||
      (trimmed.lens || null) !== (shot.camera_spec.lens ?? null))
  ) {
    patch.camera_spec = {
      shot_size: trimmed.shot_size,
      angle: trimmed.angle,
      movement: trimmed.movement,
      lens: trimmed.lens || null,
    };
  }
  if (
    trimmed.subject &&
    trimmed.action &&
    (trimmed.subject !== shot.performance_spec.subject ||
      trimmed.action !== shot.performance_spec.action ||
      (trimmed.emotion || null) !== (shot.performance_spec.emotion ?? null))
  ) {
    patch.performance_spec = {
      subject: trimmed.subject,
      action: trimmed.action,
      emotion: trimmed.emotion || null,
    };
  }
  if (draft.transition !== shot.transition) patch.transition = draft.transition as ShotTransition;
  if ((trimmed.extra_direction || null) !== (shot.extra_direction ?? null))
    patch.extra_direction = trimmed.extra_direction || null;
  if ((draft.framing.trim() || null) !== (shot.framing ?? null))
    patch.framing = draft.framing.trim() || null;
  if ((draft.screen_direction.trim() || null) !== (shot.screen_direction ?? null))
    patch.screen_direction = draft.screen_direction.trim() || null;
  if ((draft.dialogue.trim() || null) !== (shot.dialogue ?? null))
    patch.dialogue = draft.dialogue.trim() || null;
  if ((draft.speaker.trim() || null) !== (shot.speaker ?? null))
    patch.speaker = draft.speaker.trim() || null;
  if ((draft.motion_desc.trim() || null) !== (shot.motion_desc ?? null))
    patch.motion_desc = draft.motion_desc.trim() || null;

  const dirty = Object.keys(patch).length > 0;

  async function save() {
    if (!dirty || !durationValid || missingRequired || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onUpdate(patch); // parent refreshes the storyboard → shot prop catches up
    } catch (e) {
      setSaveError(errMsg(e));
    } finally {
      setSaving(false);
    }
  }

  /** Persist the cast choice on the shot — generate uses it by default from now on. */
  async function pickCast(id: string) {
    if (castSaving || id === charId) return;
    const prev = charId;
    setCharId(id);
    setCastSaving(true);
    setCastError(null);
    try {
      await onUpdate({ character_id: id || null });
    } catch (e) {
      setCharId(prev);
      setCastError(errMsg(e));
    } finally {
      setCastSaving(false);
    }
  }

  /** Still vs motion: a still freezes the keyframe into a clip (image cost, no video spend). */
  async function pickRenderMode(mode: "video" | "still") {
    if (modeSaving || mode === renderMode) return;
    const prev = renderMode;
    setRenderMode(mode);
    setModeSaving(true);
    try {
      await onUpdate({ render_mode: mode });
    } catch {
      setRenderMode(prev);
    } finally {
      setModeSaving(false);
    }
  }

  const content = (
    <>
      {/* header */}
      <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <Eyebrow>
            Shot #{shot.order + 1} · scene {shot.scene_order + 1}
          </Eyebrow>
          <h2 className="title mt-1 truncate text-2xl text-fg">{shot.purpose}</h2>
        </div>
        <button
          onClick={onClose}
          aria-label="Close inspector"
          className="-mr-2 -mt-1 inline-flex size-10 shrink-0 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <X size={18} aria-hidden />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
        {/* player(s) */}
        <div className={cn("grid gap-2", comparing && compare ? "grid-cols-2" : "grid-cols-1")}>
          <TakePlayer
            v={active}
            aspect={aspect}
            running={jobRunning && !active}
            label={active ? `Take ${takeIndex(active)}` : undefined}
            onUse={active && comparing ? () => onPick(active.id) : undefined}
          />
          {comparing && compare && (
            <TakePlayer
              v={compare}
              aspect={aspect}
              running={false}
              label={`Take ${takeIndex(compare)}`}
              onUse={() => onPick(compare.id)}
            />
          )}
        </div>

        {/* takes strip */}
        {finished.length > 0 && (
          <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Takes">
            <span className="font-mono text-[0.7rem] text-faint">takes</span>
            {finished.map((v, i) => {
              const isActive = v.id === active?.id;
              const isCompare = comparing && v.id === compare?.id;
              return (
                <button
                  key={v.id}
                  role="radio"
                  aria-checked={isActive}
                  aria-label={`Take ${i + 1}${v.selected ? " (in cut)" : ""}`}
                  onClick={() => {
                    if (comparing && !isActive) setCompareId(v.id);
                    else setActiveId(v.id);
                  }}
                  className={cn(
                    "relative grid size-10 place-items-center rounded-full border font-mono text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                    isActive
                      ? "border-accent bg-accent/20 text-accent"
                      : isCompare
                        ? "border-fg/60 text-fg"
                        : "border-border text-faint hover:text-fg",
                  )}
                >
                  {i + 1}
                  {v.selected && (
                    <span
                      aria-hidden
                      title="In the cut"
                      className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full bg-accent"
                    />
                  )}
                </button>
              );
            })}
            {finished.length > 1 && (
              <button
                onClick={() => {
                  setComparing((c) => !c);
                  if (!compare) {
                    const alt = finished.find((v) => v.id !== active?.id);
                    if (alt) setCompareId(alt.id);
                  }
                }}
                aria-pressed={comparing}
                className={cn(
                  "ml-1 inline-flex min-h-10 items-center gap-1.5 rounded-[var(--radius)] px-2.5 font-mono text-[0.7rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  comparing ? "bg-panel-hi text-accent" : "text-faint hover:text-fg",
                )}
              >
                <Columns2 size={13} aria-hidden /> A/B
              </button>
            )}
            {active && !active.selected && !comparing && (
              <button
                onClick={() => onPick(active.id)}
                className="ml-auto min-h-10 rounded-[var(--radius)] px-2 font-mono text-[0.7rem] text-accent transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                use in cut
              </button>
            )}
          </div>
        )}

        {/* section switch — the stage (player+takes) stays above; this declutters the scroll */}
        <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Inspector section">
          {(["review", "direction"] as const).map((sec) => (
            <button
              key={sec}
              role="tab"
              aria-selected={section === sec}
              onClick={() => setSection(sec)}
              className={cn(
                "relative -mb-px flex items-center gap-1.5 px-3 py-2 font-mono text-xs capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                section === sec ? "border-b-2 border-accent text-accent" : "text-faint hover:text-fg",
              )}
            >
              {sec}
              {sec === "review" && active?.review && (
                <ScoreBadge score={active.review.score} verdict={active.review.verdict} />
              )}
              {sec === "direction" && dirty && (
                <span className="size-1.5 rounded-full bg-run" aria-label="unsaved" />
              )}
            </button>
          ))}
        </div>

        {/* AI review */}
        {section === "review" &&
          (active?.review ? (
          <Panel className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Eyebrow>AI dailies review</Eyebrow>
                <ScoreBadge score={active.review.score} verdict={active.review.verdict} />
                <StatusBadge status={active.review.verdict === "pass" ? "accepted" : "draft"} />
              </div>
              <button
                onClick={rereview}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-[var(--radius)] px-2 font-mono text-[0.7rem] text-faint transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {reviewing ? <Spinner className="size-3" /> : <RefreshCw size={12} aria-hidden />}
                re-review
              </button>
            </div>
            <ul className="mt-2 space-y-1">
              {active.review.notes.map((n) => (
                <li key={n} className="flex gap-2 text-sm text-muted">
                  <span aria-hidden className="mt-1.5 size-1 shrink-0 rounded-full bg-faint" />
                  {n}
                </li>
              ))}
            </ul>
            {(active.review.continuity_notes ?? []).length > 0 && (
              <div className="mt-2 rounded-[var(--radius)] border border-run/40 bg-run/5 px-2.5 py-2">
                <p className="font-mono text-[0.65rem] uppercase tracking-widest text-run">
                  continuity vs previous shot
                </p>
                <ul className="mt-1 space-y-1">
                  {(active.review.continuity_notes ?? []).map((n) => (
                    <li key={n} className="flex gap-2 text-xs text-muted">
                      <span aria-hidden className="mt-1.5 size-1 shrink-0 rounded-full bg-run" />
                      {n}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {active.review.suggestions.length > 0 && (
              <div className="mt-3 flex flex-col gap-1.5">
                {active.review.suggestions.map((s) => (
                  <button
                    key={s.instruction}
                    onClick={() =>
                      s.kind === "edit" ? onEdit(active.id, s.instruction) : onGenerate()
                    }
                    disabled={jobRunning}
                    className="group flex items-center gap-2 rounded-[var(--radius)] border border-border bg-bg-soft px-2.5 py-2 text-left font-mono text-[0.7rem] text-muted transition-colors hover:border-accent/40 hover:text-fg disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <Sparkles size={12} className="shrink-0 text-accent" aria-hidden />
                    <span className="min-w-0 flex-1">{s.instruction}</span>
                    <span className="shrink-0 text-faint group-hover:text-accent">
                      {s.kind === "edit" ? "apply edit" : "retake"} →
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Panel>
          ) : (
            <p className="px-1 py-6 text-center text-sm text-faint">
              No review yet — generate a take to see the AI dailies review.
            </p>
          ))}

        {/* direction — editable; saved via PATCH and fed into the next generation */}
        {section === "direction" && (
        <Panel className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Eyebrow>Direction</Eyebrow>
            {dirty && !saving && (
              <span className="font-mono text-[0.65rem] text-run">unsaved changes</span>
            )}
          </div>
          <div className="mt-3 space-y-3">
            <Field label="render" htmlFor="dir-render-mode">
              <div id="dir-render-mode" className="flex gap-1.5">
                {(["video", "still"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={modeSaving}
                    onClick={() => pickRenderMode(m)}
                    className={cn(
                      "flex-1 rounded-md border px-2 py-1.5 text-xs transition-colors disabled:opacity-50",
                      renderMode === m
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-border text-muted hover:text-fg",
                    )}
                  >
                    {m === "still" ? "still (freeze)" : "video"}
                  </button>
                ))}
              </div>
            </Field>
            {shot.suggest_still && renderMode === "video" && (
              <p className="text-[0.65rem] text-muted">
                Low motion — a still render would skip a video generation and cost less.
              </p>
            )}
            <Field label="purpose" htmlFor="dir-purpose">
              <input
                id="dir-purpose"
                value={draft.purpose}
                onChange={set("purpose")}
                className={inputCls}
              />
            </Field>
            <Field label="beat" htmlFor="dir-beat">
              <textarea
                id="dir-beat"
                rows={2}
                value={draft.beat}
                onChange={set("beat")}
                className={cn(inputCls, "resize-none")}
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="shot size" htmlFor="dir-shot-size">
                <input
                  id="dir-shot-size"
                  value={draft.shot_size}
                  onChange={set("shot_size")}
                  className={inputCls}
                />
              </Field>
              <Field label="angle" htmlFor="dir-angle">
                <input
                  id="dir-angle"
                  value={draft.angle}
                  onChange={set("angle")}
                  className={inputCls}
                />
              </Field>
              <Field label="movement" htmlFor="dir-movement">
                <input
                  id="dir-movement"
                  value={draft.movement}
                  onChange={set("movement")}
                  className={inputCls}
                />
              </Field>
              <Field label="lens" htmlFor="dir-lens">
                <input
                  id="dir-lens"
                  value={draft.lens}
                  onChange={set("lens")}
                  placeholder="optional"
                  className={inputCls}
                />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="subject" htmlFor="dir-subject">
                <input
                  id="dir-subject"
                  value={draft.subject}
                  onChange={set("subject")}
                  className={inputCls}
                />
              </Field>
              <Field label="emotion" htmlFor="dir-emotion">
                <input
                  id="dir-emotion"
                  value={draft.emotion}
                  onChange={set("emotion")}
                  placeholder="optional"
                  className={inputCls}
                />
              </Field>
            </div>
            <Field label="action" htmlFor="dir-action">
              <input
                id="dir-action"
                value={draft.action}
                onChange={set("action")}
                className={inputCls}
              />
            </Field>
            <Field label="duration (seconds, max 15)" htmlFor="dir-duration">
              <input
                id="dir-duration"
                type="number"
                min={0.5}
                max={15}
                step={0.5}
                value={draft.duration_sec}
                onChange={set("duration_sec")}
                aria-invalid={!durationValid}
                className={cn(inputCls, "w-28", !durationValid && "border-fail/60")}
              />
            </Field>
            <div className="min-w-0">
              <span className="font-mono text-[0.65rem] uppercase tracking-widest text-faint">
                transition to next shot
              </span>
              <div
                className="mt-1 flex flex-wrap gap-1.5"
                role="radiogroup"
                aria-label="Transition to next shot"
              >
                {TRANSITIONS.map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="radio"
                    aria-checked={draft.transition === t}
                    onClick={() => setDraft((d) => ({ ...d, transition: t }))}
                    className={cn(
                      "min-h-9 rounded-full border px-2.5 font-mono text-[0.65rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                      draft.transition === t
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-border text-faint hover:text-fg",
                    )}
                  >
                    {t.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>
            <Field label="framing (blocking: positions + facing + focus)" htmlFor="dir-framing">
              <input
                id="dir-framing"
                value={draft.framing}
                onChange={set("framing")}
                placeholder="e.g. “Maya on left third, facing right, focus on her hands”"
                className={inputCls}
              />
            </Field>
            <Field label="screen direction (180° line)" htmlFor="dir-screen-direction">
              <input
                id="dir-screen-direction"
                value={draft.screen_direction}
                onChange={set("screen_direction")}
                placeholder="e.g. “moving left-to-right”, “facing camera-right”"
                className={inputCls}
              />
            </Field>
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Field label="dialogue (spoken line)" htmlFor="dir-dialogue">
                <input
                  id="dir-dialogue"
                  value={draft.dialogue}
                  onChange={set("dialogue")}
                  placeholder="the one line spoken in this shot"
                  className={inputCls}
                />
              </Field>
              <Field label="speaker" htmlFor="dir-speaker">
                <input
                  id="dir-speaker"
                  value={draft.speaker}
                  onChange={set("speaker")}
                  placeholder="narrator"
                  className={cn(inputCls, "w-28")}
                />
              </Field>
            </div>
            <Field label="motion (between the planned key frames)" htmlFor="dir-motion">
              <textarea
                id="dir-motion"
                rows={2}
                value={draft.motion_desc}
                onChange={set("motion_desc")}
                placeholder="camera terms + appearance-anchored subjects — drives the video prompt"
                className={cn(inputCls, "resize-none")}
              />
            </Field>
            <Field label="director's notes" htmlFor="dir-extra">
              <textarea
                id="dir-extra"
                rows={2}
                value={draft.extra_direction}
                onChange={set("extra_direction")}
                placeholder="goes straight into the generation prompt — e.g. “rain-streaked window, neon reflections”"
                className={cn(inputCls, "resize-none")}
              />
            </Field>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                onClick={save}
                loading={saving}
                disabled={!dirty || !durationValid || missingRequired}
              >
                Save direction
              </Button>
              {(dirty || missingRequired) && !saving && (
                <Button variant="ghost" onClick={() => setDraft(fromShot(shot))}>
                  Discard
                </Button>
              )}
              {!durationValid && (
                <span className="font-mono text-[0.7rem] text-fail">
                  duration must be &gt;0 and ≤15s
                </span>
              )}
              {missingRequired && (
                <span className="font-mono text-[0.7rem] text-fail">
                  purpose, beat, camera and performance fields can&apos;t be empty
                </span>
              )}
              {saveError && <span className="font-mono text-[0.7rem] text-fail">{saveError}</span>}
            </div>
          </div>
          {active?.routing_note && (
            <p className="mt-3 border-t border-border pt-2.5 font-mono text-[0.75rem]">
              <span className="text-faint">routing — </span>
              <span className="text-accent/90">{active.routing_note}</span>
            </p>
          )}
          {shot.acceptance_rules.length > 0 && (
            <div className="mt-3 border-t border-border pt-2.5">
              <p className="font-mono text-[0.65rem] uppercase tracking-widest text-faint">
                acceptance rules
              </p>
              <ul className="mt-1.5 space-y-1">
                {shot.acceptance_rules.map((r) => (
                  <li key={String(r)} className="flex gap-2 text-xs text-muted">
                    <span aria-hidden className="text-accent">
                      ▸
                    </span>
                    {String(r)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {active?.prompt != null && active.prompt !== "" && (
            <details className="mt-3 border-t border-border pt-2.5">
              <summary className="cursor-pointer font-mono text-[0.65rem] uppercase tracking-widest text-faint transition-colors hover:text-fg">
                generation prompt
              </summary>
              <p className="mt-1.5 font-mono text-[0.7rem] leading-relaxed text-muted">
                {active.prompt}
              </p>
            </details>
          )}
        </Panel>
        )}

        {/* failure */}
        {!active &&
          !jobRunning &&
          versions.some((v) => v.job_status === "failed") && (
            <Panel className="border-fail/40 p-4">
              <div className="flex items-center gap-2">
                <StatusBadge status="failed" />
                <span className="text-xs text-faint">
                  {versions.find((v) => v.job_status === "failed")?.failure_reason ??
                    "Generation failed"}
                </span>
              </div>
            </Panel>
          )}
      </div>

      {/* actions */}
      <div className="space-y-3 border-t border-border px-5 py-4">
        {characters.length > 0 && (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[0.65rem] text-faint">cast:</span>
              {[{ id: "", name: "none" }, ...characters].map((c) => (
                <button
                  key={c.id || "none"}
                  onClick={() => pickCast(c.id)}
                  aria-pressed={charId === c.id}
                  disabled={castSaving}
                  className={cn(
                    "min-h-9 rounded-full border px-2.5 font-mono text-[0.65rem] transition-colors disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                    charId === c.id
                      ? "border-accent text-accent"
                      : "border-border text-faint hover:text-fg",
                  )}
                >
                  {c.name}
                </button>
              ))}
              {castSaving ? (
                <Spinner className="size-3" />
              ) : (
                <span className="font-mono text-[0.6rem] text-faint">
                  saved to shot — used by default
                </span>
              )}
            </div>
            {castError && <p className="font-mono text-[0.7rem] text-fail">{castError}</p>}
          </>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            loading={jobRunning}
            onClick={() =>
              onGenerate({
                ...(charId ? { character_id: charId } : {}),
                ...(numTakes > 1 ? { num_takes: numTakes } : {}),
              })
            }
          >
            {finished.length ? "+ New take" : "Generate shot"}
            {numTakes > 1 ? ` ×${numTakes}` : ""}
          </Button>
          <div
            className="flex items-center gap-1"
            role="radiogroup"
            aria-label="Takes per generation (best-of-N, winner auto-selected by review)"
          >
            {[1, 2, 3].map((n) => (
              <button
                key={n}
                role="radio"
                aria-checked={numTakes === n}
                onClick={() => setNumTakes(n)}
                title={
                  n === 1
                    ? "One take"
                    : `${n} takes with the same direction — the highest-scoring pass is auto-selected`
                }
                className={cn(
                  "min-h-9 rounded-full border px-2.5 font-mono text-[0.65rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  numTakes === n
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border text-faint hover:text-fg",
                )}
              >
                ×{n}
              </button>
            ))}
          </div>
          {canContinue && (
            <Button
              loading={jobRunning}
              onClick={() =>
                onGenerate({
                  continue_from_previous: true,
                  ...(charId ? { character_id: charId } : {}),
                })
              }
              title="Seed this shot with the previous shot's last frame (i2v continuation)"
            >
              <ArrowRightToLine size={14} aria-hidden /> Continue from #{shot.order}
            </Button>
          )}
          <Button
            loading={jobRunning}
            onClick={onKeyframe}
            title="Generate the planned opening frame as an image (refinable; anchors the next render)"
          >
            <ImagePlus size={14} aria-hidden />
            {shot.keyframe_frame_id ? "Re-keyframe" : "Keyframe"}
          </Button>
          {shot.dialogue && (
            <Button
              loading={jobRunning}
              onClick={onVoiceover}
              title="Synthesize this shot's spoken line as a voiceover (TTS)"
            >
              <Volume2 size={14} aria-hidden />
              {shot.vo_asset_id ? "Re-voice" : "Voiceover"}
            </Button>
          )}
        </div>
        {active && (
          <div className="flex items-center gap-2">
            <label className="sr-only" htmlFor="director-note">
              Director&apos;s note
            </label>
            <input
              id="director-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendNote()}
              disabled={jobRunning}
              placeholder="director's note — “change the background to night” (videoedit)"
              className="min-w-0 flex-1 rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 font-mono text-xs text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
            <Button onClick={sendNote} disabled={!note.trim() || jobRunning}>
              Revise
            </Button>
          </div>
        )}
      </div>
    </>
  );

  // docked: a persistent right pane (the workstation's third column). Otherwise a modal
  // drawer — the mobile fallback where a side-by-side split would be too narrow.
  if (docked) {
    return (
      <section
        aria-label={`Shot ${shot.order + 1} inspector`}
        className="flex h-full min-h-0 flex-col bg-bg"
      >
        {content}
      </section>
    );
  }
  return (
    <Drawer open onClose={onClose} label={`Shot ${shot.order + 1} inspector`}>
      {content}
    </Drawer>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <label
        htmlFor={htmlFor}
        className="font-mono text-[0.65rem] uppercase tracking-widest text-faint"
      >
        {label}
      </label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function TakePlayer({
  v,
  aspect,
  running,
  label,
  onUse,
}: {
  v?: ShotVersion;
  aspect: string;
  running: boolean;
  label?: string;
  onUse?: () => void;
}) {
  const playable = v && isPlayable(v.video_url);
  return (
    <div>
      <div
        className={cn(
          "relative overflow-hidden rounded-[var(--radius)] border border-border bg-bg-soft",
          aspectClass(aspect),
        )}
      >
        {playable ? (
          <video
            src={v.video_url!}
            poster={isPlayable(v.thumbnail_url) ? v.thumbnail_url : undefined}
            controls
            className="size-full object-cover"
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-2 p-3 text-center">
            {running ? (
              <>
                <Spinner className="size-6 text-accent opacity-100" />
                <StatusBadge status="running" />
              </>
            ) : v ? (
              <>
                <StatusBadge status="succeeded" />
                <span className="font-mono text-[0.65rem] text-faint">
                  rendered — preview unavailable (mock)
                </span>
              </>
            ) : (
              <span className="font-mono text-[0.65rem] text-faint">no take yet</span>
            )}
          </div>
        )}
        {label && (
          <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.65rem] text-fg backdrop-blur">
            {label}
          </span>
        )}
      </div>
      {v && (
        <div className="mt-1.5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 font-mono text-[0.65rem] text-faint">
            {v.model && <Pill>{v.model.split(":").pop()!.replace("wan2.7-", "")}</Pill>}
            {v.duration_sec != null && <span>{v.duration_sec.toFixed(1)}s</span>}
            {v.score != null && <ScoreBadge score={v.score} verdict={v.review?.verdict} />}
          </div>
          {onUse && (
            <button
              onClick={onUse}
              className="min-h-9 rounded-[var(--radius)] px-2 font-mono text-[0.7rem] text-accent transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {v.selected ? "★ in cut" : "use this take"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
