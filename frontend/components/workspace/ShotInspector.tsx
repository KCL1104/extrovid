"use client";

import { useState } from "react";
import { ArrowRightToLine, Columns2, RefreshCw, Sparkles, X } from "lucide-react";
import type { Character, Shot, ShotVersion } from "@/lib/api";
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
  cameraLine,
  chosenTake,
  isPlayable,
  isRunning,
} from "@/components/workspace/shared";

export default function ShotInspector({
  shot,
  versions,
  characters,
  aspect,
  canContinue,
  busy,
  onClose,
  onGenerate,
  onEdit,
  onPick,
  onReview,
}: {
  shot: Shot | null;
  versions: ShotVersion[];
  characters: Character[];
  aspect: string;
  canContinue: boolean;
  busy: boolean;
  onClose: () => void;
  onGenerate: (opts?: { character_id?: string; continue_from_previous?: boolean }) => void;
  onEdit: (versionId: string, instruction: string) => void;
  onPick: (versionId: string) => void;
  onReview: (versionId: string) => Promise<void>;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [charId, setCharId] = useState("");
  const [note, setNote] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const finished = versions.filter((v) => v.output_asset_id);
  const fallback = chosenTake(versions);
  const active = finished.find((v) => v.id === activeId) ?? fallback;
  const compare = finished.find((v) => v.id === compareId && v.id !== active?.id);
  const jobRunning = busy || versions.some(isRunning);

  // per-shot state resets via the `key={shot.id}` the parent passes — no effect needed

  if (!shot) return null;

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

  return (
    <Drawer open onClose={onClose} label={`Shot ${shot.order + 1} inspector`}>
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

        {/* AI review */}
        {active?.review && (
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
        )}

        {/* direction */}
        <Panel className="p-4">
          <Eyebrow>Direction</Eyebrow>
          <dl className="mt-2 space-y-1.5 font-mono text-[0.75rem]">
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-faint">camera</dt>
              <dd className="text-muted">{cameraLine(shot)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-faint">action</dt>
              <dd className="text-muted">
                {shot.performance_spec.subject}: {shot.performance_spec.action}
                {shot.performance_spec.emotion ? ` (${shot.performance_spec.emotion})` : ""}
              </dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-faint">beat</dt>
              <dd className="text-muted">{shot.beat}</dd>
            </div>
            {active?.routing_note && (
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-faint">routing</dt>
                <dd className="text-accent/90">{active.routing_note}</dd>
              </div>
            )}
          </dl>
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
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[0.65rem] text-faint">cast:</span>
            {[{ id: "", name: "none" }, ...characters].map((c) => (
              <button
                key={c.id || "none"}
                onClick={() => setCharId(c.id)}
                aria-pressed={charId === c.id}
                className={cn(
                  "min-h-9 rounded-full border px-2.5 font-mono text-[0.65rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  charId === c.id
                    ? "border-accent text-accent"
                    : "border-border text-faint hover:text-fg",
                )}
              >
                {c.name}
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            loading={jobRunning}
            onClick={() => onGenerate(charId ? { character_id: charId } : undefined)}
          >
            {finished.length ? "+ New take" : "Generate shot"}
          </Button>
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
    </Drawer>
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
