"use client";

import { useState } from "react";
import { ArrowLeft, ArrowRight, GripVertical, RotateCcw, X } from "lucide-react";
import type { ClipSpec, RoughCut, Shot, ShotVersion } from "@/lib/api";
import {
  Button,
  EmptyState,
  Eyebrow,
  Panel,
  Pill,
  StatusBadge,
  Toggle,
  cn,
} from "@/components/ui";
import {
  aspectClass,
  chosenTake,
  isPlayable,
  relTime,
} from "@/components/workspace/shared";

type PlanRow = {
  shotId: string; // identity is the SHOT, so re-selecting a take keeps the clip's slot + trims
  shot_version_id: string;
  shotOrder: number;
  purpose: string;
  duration: number;
  thumb: string | null;
  in_sec: string; // text for friendly editing; parsed on assemble
  out_sec: string;
};

const fmt = (sec: number) => {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

// effective on-screen length of a clip given its in/out trim
const effDur = (r: PlanRow) => {
  const i = parseFloat(r.in_sec) || 0;
  const o = parseFloat(r.out_sec);
  return Number.isFinite(o) && o > i ? o - i : Math.max(0, r.duration - i);
};

export default function CutPlanner({
  shots,
  versions,
  roughCuts,
  aspect,
  assembling,
  publishing,
  onAssemble,
  onTogglePublish,
}: {
  shots: Shot[];
  versions: Record<string, ShotVersion[]>;
  roughCuts: RoughCut[];
  aspect: string;
  assembling: boolean;
  publishing: string | null;
  onAssemble: (clips: ClipSpec[], captions: boolean, music: boolean) => void;
  onTogglePublish: (rc: RoughCut) => void;
}) {
  const [rows, setRows] = useState<PlanRow[]>([]);
  const [captions, setCaptions] = useState(true);
  const [music, setMusic] = useState(true);
  const [selected, setSelected] = useState<string | null>(null); // selected shotId for trim
  const [dragId, setDragId] = useState<string | null>(null);

  // shots that have a take to represent them in the cut, in storyboard order
  const available = shots
    .map((s) => ({ s, take: chosenTake(versions[s.id] ?? []) }))
    .filter((x): x is { s: Shot; take: ShotVersion } => !!x.take);

  const rowFor = (s: Shot, take: ShotVersion, prev?: PlanRow): PlanRow => ({
    shotId: s.id,
    shot_version_id: take.id,
    shotOrder: s.order,
    purpose: s.purpose,
    duration: take.duration_sec ?? s.duration_sec,
    thumb: isPlayable(take.thumbnail_url) ? take.thumbnail_url : null,
    in_sec: prev?.in_sec ?? "",
    out_sec: prev?.out_sec ?? "",
  });

  const freshRows = (): PlanRow[] => available.map(({ s, take }) => rowFor(s, take));

  // Merge takes into the plan WITHOUT discarding the user's hand-built order or trims:
  // existing clips keep their slot (and in/out), new shots append, vanished shots drop.
  // (Previously this rebuilt every row on each poll, wiping a hand-edited cut — fixed.)
  const planKey = available.map((x) => `${x.s.id}:${x.take.id}`).join(",");
  const [prevKey, setPrevKey] = useState<string | null>(null);
  if (prevKey !== planKey) {
    setPrevKey(planKey);
    const byShot = new Map(available.map((x) => [x.s.id, x]));
    setRows((prev) => {
      const kept = prev
        .filter((r) => byShot.has(r.shotId))
        .map((r) => {
          const { s, take } = byShot.get(r.shotId)!;
          return rowFor(s, take, r); // refresh version/thumb/duration, preserve trims
        });
      const keptIds = new Set(kept.map((r) => r.shotId));
      const added = available
        .filter((x) => !keptIds.has(x.s.id))
        .map((x) => rowFor(x.s, x.take));
      return [...kept, ...added];
    });
  }

  const reorder = (fromId: string, toId: string) =>
    setRows((r) => {
      const from = r.findIndex((x) => x.shotId === fromId);
      const to = r.findIndex((x) => x.shotId === toId);
      if (from < 0 || to < 0 || from === to) return r;
      const next = [...r];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });

  const move = (id: string, dir: -1 | 1) =>
    setRows((r) => {
      const i = r.findIndex((x) => x.shotId === id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= r.length) return r;
      const next = [...r];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const setTrim = (id: string, key: "in_sec" | "out_sec", value: string) =>
    setRows((r) => r.map((row) => (row.shotId === id ? { ...row, [key]: value } : row)));

  const removeRow = (id: string) => {
    setRows((r) => r.filter((x) => x.shotId !== id));
    if (selected === id) setSelected(null);
  };

  function assemble() {
    const clips: ClipSpec[] = rows.map((r) => {
      const inSec = parseFloat(r.in_sec);
      const outSec = parseFloat(r.out_sec);
      return {
        shot_version_id: r.shot_version_id,
        ...(Number.isFinite(inSec) && inSec > 0 ? { in_sec: inSec } : {}),
        ...(Number.isFinite(outSec) && outSec > 0 ? { out_sec: outSec } : {}),
      };
    });
    onAssemble(clips, captions, music);
  }

  const totalSec = rows.reduce((acc, r) => acc + effDur(r), 0);
  const selectedRow = rows.find((r) => r.shotId === selected);

  if (shots.length === 0) {
    return (
      <EmptyState
        title="Nothing to cut yet"
        hint="Plan the production and generate shots first — selected takes line up here for assembly."
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* timeline */}
      <Panel className="rise p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Eyebrow>Timeline</Eyebrow>
            {rows.length > 0 && (
              <Pill>
                {rows.length} clips · {fmt(totalSec)}
              </Pill>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Toggle checked={captions} onChange={setCaptions} label="captions" />
            <Toggle checked={music} onChange={setMusic} label="ambient bed" />
            <Button
              variant="ghost"
              onClick={() => {
                setRows(freshRows());
                setSelected(null);
              }}
              title="Reset order and trims to the storyboard"
            >
              <RotateCcw size={13} aria-hidden /> Reset
            </Button>
            <Button
              variant="primary"
              onClick={assemble}
              loading={assembling}
              disabled={rows.length === 0}
            >
              Assemble cut
            </Button>
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="mt-4 text-sm text-faint">
            Generate at least one shot — the selected take of each shot joins the cut.
          </p>
        ) : (
          <>
            {/* ruler */}
            <div className="mt-4 flex items-center justify-between font-mono text-[0.6rem] text-faint">
              <span>0:00</span>
              <span>{fmt(totalSec)}</span>
            </div>
            {/* proportional clip track — widths scale with each clip's trimmed duration */}
            <div className="mt-1 flex gap-1 overflow-x-auto rounded-[var(--radius)] border border-border bg-bg-soft p-1">
              {rows.map((r) => {
                const pct = totalSec ? (effDur(r) / totalSec) * 100 : 100 / rows.length;
                const isSel = r.shotId === selected;
                return (
                  <button
                    key={r.shotId}
                    draggable
                    onDragStart={() => setDragId(r.shotId)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (dragId) reorder(dragId, r.shotId);
                      setDragId(null);
                    }}
                    onDragEnd={() => setDragId(null)}
                    onClick={() => setSelected(isSel ? null : r.shotId)}
                    style={{ flexBasis: `${pct}%` }}
                    aria-label={`Clip ${r.shotOrder + 1}: ${r.purpose} (${effDur(r).toFixed(1)}s)`}
                    aria-pressed={isSel}
                    className={cn(
                      "group relative grid min-w-16 shrink-0 grow-0 cursor-grab place-items-end overflow-hidden rounded border text-left transition-colors active:cursor-grabbing focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                      aspectClass(aspect) === "aspect-video" ? "h-16" : "h-20",
                      isSel
                        ? "border-accent ring-1 ring-accent"
                        : "border-border-hi hover:border-accent/50",
                      dragId === r.shotId && "opacity-40",
                    )}
                  >
                    {r.thumb ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={r.thumb} alt="" className="absolute inset-0 size-full object-cover" />
                    ) : (
                      <span className="absolute inset-0 bg-panel" aria-hidden />
                    )}
                    <span className="relative z-10 flex w-full items-center justify-between gap-1 bg-gradient-to-t from-black/80 to-transparent px-1.5 pb-1 pt-3 font-mono text-[0.6rem] text-fg">
                      <span className="flex items-center gap-0.5">
                        <GripVertical
                          size={10}
                          className="opacity-60 group-hover:opacity-100"
                          aria-hidden
                        />
                        #{r.shotOrder + 1}
                      </span>
                      <span>{effDur(r).toFixed(1)}s</span>
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="mt-1.5 font-mono text-[0.6rem] text-faint">
              drag clips to reorder · click a clip to trim it
            </p>

            {/* selected-clip editor — trim is always available here (no longer hidden on mobile) */}
            {selectedRow && (
              <div className="mt-3 rounded-[var(--radius)] border border-accent/40 bg-bg-soft p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-sm text-fg">
                    <span className="mr-1.5 font-mono text-[0.7rem] text-accent">
                      #{selectedRow.shotOrder + 1}
                    </span>
                    {selectedRow.purpose}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={() => move(selectedRow.shotId, -1)}
                      disabled={rows[0]?.shotId === selectedRow.shotId}
                      aria-label="Move clip earlier"
                      className="grid size-8 place-items-center rounded text-faint transition-colors hover:text-fg disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      <ArrowLeft size={14} aria-hidden />
                    </button>
                    <button
                      onClick={() => move(selectedRow.shotId, 1)}
                      disabled={rows[rows.length - 1]?.shotId === selectedRow.shotId}
                      aria-label="Move clip later"
                      className="grid size-8 place-items-center rounded text-faint transition-colors hover:text-fg disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      <ArrowRight size={14} aria-hidden />
                    </button>
                    <button
                      onClick={() => removeRow(selectedRow.shotId)}
                      aria-label="Remove clip from the cut"
                      className="grid size-8 place-items-center rounded text-faint transition-colors hover:text-fail focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      <X size={14} aria-hidden />
                    </button>
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1.5 font-mono text-[0.65rem] text-faint">
                    in
                    <input
                      type="number"
                      min={0}
                      step={0.1}
                      value={selectedRow.in_sec}
                      onChange={(e) => setTrim(selectedRow.shotId, "in_sec", e.target.value)}
                      placeholder="0"
                      className="w-20 rounded border border-border bg-bg px-1.5 py-1 text-right text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent"
                    />
                  </label>
                  <label className="flex items-center gap-1.5 font-mono text-[0.65rem] text-faint">
                    out
                    <input
                      type="number"
                      min={0}
                      step={0.1}
                      value={selectedRow.out_sec}
                      onChange={(e) => setTrim(selectedRow.shotId, "out_sec", e.target.value)}
                      placeholder={selectedRow.duration.toFixed(1)}
                      className="w-20 rounded border border-border bg-bg px-1.5 py-1 text-right text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent"
                    />
                  </label>
                  <span className="font-mono text-[0.6rem] text-faint">
                    source {selectedRow.duration.toFixed(1)}s → {effDur(selectedRow).toFixed(1)}s in cut
                  </span>
                </div>
              </div>
            )}
          </>
        )}
      </Panel>

      {/* rendered cuts */}
      <section>
        <Eyebrow>Cuts · {roughCuts.length}</Eyebrow>
        {roughCuts.length === 0 ? (
          <p className="mt-3 text-sm text-faint">No cuts assembled yet.</p>
        ) : (
          <div className="mt-4 space-y-4">
            {roughCuts.map((rc, i) => (
              <Panel key={rc.id} className="rise overflow-hidden p-5" style={{ animationDelay: `${i * 60}ms` }}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={rc.status} />
                    <Pill>{rc.shot_version_ids.length} clips</Pill>
                    {rc.options && (
                      <span className="font-mono text-[0.65rem] text-faint">
                        {rc.options.captions ? "captions" : "no captions"} ·{" "}
                        {rc.options.music ? "ambient bed" : "no music"}
                      </span>
                    )}
                    <span className="font-mono text-[0.65rem] text-faint">
                      {relTime(rc.created_at)}
                    </span>
                  </div>
                  {isPlayable(rc.video_url) && (
                    <div className="flex items-center gap-4">
                      <button
                        onClick={() => onTogglePublish(rc)}
                        disabled={publishing === rc.id}
                        className={cn(
                          "min-h-10 rounded-[var(--radius)] px-1 font-mono text-xs transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                          rc.published ? "text-ok hover:text-fail" : "text-muted hover:text-accent",
                        )}
                      >
                        {publishing === rc.id
                          ? "…"
                          : rc.published
                            ? "● in gallery · unpublish"
                            : "share to gallery ↗"}
                      </button>
                      <a
                        href={rc.video_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        download ↓
                      </a>
                    </div>
                  )}
                </div>
                {isPlayable(rc.video_url) ? (
                  <video
                    src={rc.video_url}
                    controls
                    className={cn("mx-auto mt-3 max-h-[70vh] rounded-[var(--radius)] bg-black", aspectClass(aspect))}
                  />
                ) : (
                  <p className="mt-3 font-mono text-xs text-faint">
                    cut assembled — preview unavailable (mock mode)
                  </p>
                )}
              </Panel>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
