"use client";

import { Play } from "lucide-react";
import type { Character, Shot, ShotVersion } from "@/lib/api";
import { Button, EmptyState, Eyebrow, Panel, ScoreBadge, Spinner, StatusBadge, cn } from "@/components/ui";
import {
  aspectClass,
  cameraLine,
  chosenTake,
  isPlayable,
  isRunning,
} from "@/components/workspace/shared";

export default function ShotBoard({
  shots,
  versions,
  characters,
  aspect,
  busy,
  generating,
  onOpen,
  onGenerate,
}: {
  shots: Shot[];
  versions: Record<string, ShotVersion[]>;
  characters: Character[];
  aspect: string;
  busy: Record<string, boolean>;
  generating: string[];
  onOpen: (shotId: string) => void;
  onGenerate: (shotId: string) => void;
}) {
  if (shots.length === 0) {
    return (
      <EmptyState
        title="No storyboard yet"
        hint="Plan the production first — the storyboard agent breaks the script into an executable shot list with camera, performance, and acceptance rules."
      />
    );
  }
  return (
    <div>
      {characters.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Eyebrow>Cast</Eyebrow>
          {characters.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-panel px-2 py-1"
            >
              <span className="size-6 shrink-0 overflow-hidden rounded-full bg-bg-soft">
                {isPlayable(c.reference_image_urls[0]) && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={c.reference_image_urls[0]} alt={c.name} className="size-full object-cover" />
                )}
              </span>
              <span className="pr-1 text-xs text-fg">{c.name}</span>
            </span>
          ))}
          <span className="text-[0.7rem] text-faint">
            Attach cast in the shot inspector for cross-shot consistency (r2v).
          </span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {shots.map((shot, i) => (
          <ShotCard
            key={shot.id}
            shot={shot}
            versions={versions[shot.id] ?? []}
            aspect={aspect}
            busy={!!busy[shot.id] || generating.includes(shot.id)}
            onOpen={() => onOpen(shot.id)}
            onGenerate={() => onGenerate(shot.id)}
            delay={i * 40}
          />
        ))}
      </div>
    </div>
  );
}

function ShotCard({
  shot,
  versions,
  aspect,
  busy,
  onOpen,
  onGenerate,
  delay,
}: {
  shot: Shot;
  versions: ShotVersion[];
  aspect: string;
  busy: boolean;
  onOpen: () => void;
  onGenerate: () => void;
  delay: number;
}) {
  const take = chosenTake(versions);
  const jobRunning = busy || versions.some(isRunning);
  const failed = !take && !jobRunning && versions.some((v) => v.job_status === "failed");
  const model = (take?.model ?? shot.preferred_model).split(":").pop()!.replace("wan2.7-", "");
  const thumb = take && isPlayable(take.thumbnail_url) ? take.thumbnail_url : null;
  const finishedCount = versions.filter((v) => v.output_asset_id).length;

  return (
    <Panel className="rise overflow-hidden" style={{ animationDelay: `${delay}ms` }}>
      <button
        onClick={onOpen}
        aria-label={`Open shot ${shot.order + 1}: ${shot.purpose}`}
        className={cn(
          "group relative block w-full bg-bg-soft text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent",
          aspectClass(aspect),
        )}
        aria-busy={jobRunning}
      >
        {thumb ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={thumb} alt="" className="size-full object-cover" />
            <span className="absolute inset-0 grid place-items-center bg-black/0 transition-colors group-hover:bg-black/30">
              <span className="grid size-12 place-items-center rounded-full bg-black/60 text-accent opacity-0 backdrop-blur transition-opacity group-hover:opacity-100">
                <Play size={18} aria-hidden />
              </span>
            </span>
          </>
        ) : (
          <span className="flex size-full flex-col items-center justify-center gap-2 p-3 text-center">
            {jobRunning ? (
              <>
                <Spinner className="size-6 text-accent opacity-100" />
                <StatusBadge status="running" />
              </>
            ) : failed ? (
              <>
                <StatusBadge status="failed" />
                <span className="px-2 font-mono text-[0.65rem] text-faint">
                  open to retry or revise
                </span>
              </>
            ) : take ? (
              <>
                <StatusBadge status="succeeded" />
                <span className="font-mono text-[0.65rem] text-faint">
                  rendered — open to direct
                </span>
              </>
            ) : (
              <span className="font-mono text-[0.65rem] text-faint">not generated</span>
            )}
          </span>
        )}
        <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.7rem] text-fg backdrop-blur">
          #{shot.order + 1} · {model}
        </span>
        <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.7rem] text-accent backdrop-blur">
          {(take?.duration_sec ?? shot.duration_sec).toFixed(1)}s
        </span>
        {take?.score != null && (
          <span className="absolute bottom-2 left-2 rounded bg-black/60 px-1.5 py-0.5 backdrop-blur">
            <ScoreBadge score={take.score} verdict={take.review?.verdict} />
          </span>
        )}
        {finishedCount > 1 && (
          <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.65rem] text-muted backdrop-blur">
            {finishedCount} takes
          </span>
        )}
      </button>
      <div className="p-4">
        <p className="text-sm text-fg">{shot.purpose}</p>
        <p className="mt-1 font-mono text-[0.7rem] leading-relaxed text-faint">
          {cameraLine(shot)} — {shot.performance_spec.subject}: {shot.performance_spec.action}
        </p>
        {!take && !jobRunning && !failed && (
          <div className="mt-3">
            <Button variant="primary" onClick={onGenerate} className="w-full justify-center">
              Generate shot
            </Button>
          </div>
        )}
      </div>
    </Panel>
  );
}
