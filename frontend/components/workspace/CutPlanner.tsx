"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, RotateCcw, X } from "lucide-react";
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
  shot_version_id: string;
  shotOrder: number;
  purpose: string;
  duration: number;
  thumb: string | null;
  in_sec: string; // keep as text for friendly editing; parsed on assemble
  out_sec: string;
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

  const buildRows = (): PlanRow[] =>
    shots.flatMap((s) => {
      const take = chosenTake(versions[s.id] ?? []);
      if (!take) return [];
      return [
        {
          shot_version_id: take.id,
          shotOrder: s.order,
          purpose: s.purpose,
          duration: take.duration_sec ?? s.duration_sec,
          thumb: isPlayable(take.thumbnail_url) ? take.thumbnail_url : null,
          in_sec: "",
          out_sec: "",
        },
      ];
    });

  // refresh the plan whenever takes change (new renders, new selections) —
  // adjust-during-render: https://react.dev/learn/you-might-not-need-an-effect
  const planKey = shots
    .map((s) => chosenTake(versions[s.id] ?? [])?.id ?? "-")
    .join(",");
  const [prevKey, setPrevKey] = useState<string | null>(null);
  if (prevKey !== planKey) {
    setPrevKey(planKey);
    setRows(buildRows());
  }

  const move = (i: number, dir: -1 | 1) =>
    setRows((r) => {
      const j = i + dir;
      if (j < 0 || j >= r.length) return r;
      const next = [...r];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const setTrim = (i: number, key: "in_sec" | "out_sec", value: string) =>
    setRows((r) => r.map((row, k) => (k === i ? { ...row, [key]: value } : row)));

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

  const totalSec = rows.reduce((acc, r) => {
    const inSec = parseFloat(r.in_sec) || 0;
    const outSec = parseFloat(r.out_sec);
    return acc + (Number.isFinite(outSec) && outSec > inSec ? outSec - inSec : r.duration - inSec);
  }, 0);

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
      {/* cut plan */}
      <Panel className="rise p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Eyebrow>Cut plan</Eyebrow>
            {rows.length > 0 && (
              <Pill>
                {rows.length} clips · ~{totalSec.toFixed(1)}s
              </Pill>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Toggle checked={captions} onChange={setCaptions} label="captions" />
            <Toggle checked={music} onChange={setMusic} label="ambient bed" />
            <Button
              variant="ghost"
              onClick={() => setRows(buildRows())}
              title="Reset order and trims to the storyboard"
            >
              <RotateCcw size={13} aria-hidden /> Reset
            </Button>
            <Button variant="primary" onClick={assemble} loading={assembling} disabled={rows.length === 0}>
              Assemble cut
            </Button>
          </div>
        </div>
        {rows.length === 0 ? (
          <p className="mt-4 text-sm text-faint">
            Generate at least one shot — the selected take of each shot joins the cut.
          </p>
        ) : (
          <ol className="mt-4 space-y-2">
            {rows.map((r, i) => (
              <li
                key={r.shot_version_id}
                className="flex items-center gap-3 rounded-[var(--radius)] border border-border bg-bg-soft p-2"
              >
                <span className="w-6 text-center font-mono text-[0.7rem] text-faint">{i + 1}</span>
                <span className="h-12 w-9 shrink-0 overflow-hidden rounded bg-panel">
                  {r.thumb && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={r.thumb} alt="" className="size-full object-cover" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg">
                    <span className="mr-1.5 font-mono text-[0.7rem] text-accent">
                      #{r.shotOrder + 1}
                    </span>
                    {r.purpose}
                  </span>
                  <span className="font-mono text-[0.65rem] text-faint">
                    {r.duration.toFixed(1)}s
                  </span>
                </span>
                <span className="hidden items-center gap-1 sm:flex">
                  <label className="font-mono text-[0.6rem] text-faint" htmlFor={`in-${i}`}>
                    in
                  </label>
                  <input
                    id={`in-${i}`}
                    type="number"
                    min={0}
                    step={0.1}
                    value={r.in_sec}
                    onChange={(e) => setTrim(i, "in_sec", e.target.value)}
                    placeholder="0"
                    className="w-16 rounded border border-border bg-bg px-1.5 py-1 text-right font-mono text-[0.7rem] text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent"
                  />
                  <label className="font-mono text-[0.6rem] text-faint" htmlFor={`out-${i}`}>
                    out
                  </label>
                  <input
                    id={`out-${i}`}
                    type="number"
                    min={0}
                    step={0.1}
                    value={r.out_sec}
                    onChange={(e) => setTrim(i, "out_sec", e.target.value)}
                    placeholder={r.duration.toFixed(1)}
                    className="w-16 rounded border border-border bg-bg px-1.5 py-1 text-right font-mono text-[0.7rem] text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent"
                  />
                </span>
                <span className="flex shrink-0 items-center">
                  <button
                    onClick={() => move(i, -1)}
                    disabled={i === 0}
                    aria-label={`Move clip ${i + 1} earlier`}
                    className="grid size-9 place-items-center rounded text-faint transition-colors hover:text-fg disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <ArrowUp size={14} aria-hidden />
                  </button>
                  <button
                    onClick={() => move(i, 1)}
                    disabled={i === rows.length - 1}
                    aria-label={`Move clip ${i + 1} later`}
                    className="grid size-9 place-items-center rounded text-faint transition-colors hover:text-fg disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <ArrowDown size={14} aria-hidden />
                  </button>
                  <button
                    onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))}
                    aria-label={`Remove clip ${i + 1} from the cut`}
                    className="grid size-9 place-items-center rounded text-faint transition-colors hover:text-fail focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <X size={14} aria-hidden />
                  </button>
                </span>
              </li>
            ))}
          </ol>
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
