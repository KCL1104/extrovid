"use client";

import { Fragment, useState } from "react";
import { Clapperboard, Film, ImageIcon, Link2, Play, Square } from "lucide-react";
import type { Character, ProduceStatus, Scene, Shot, ShotVersion } from "@/lib/api";
import { Button, EmptyState, Eyebrow, Panel, Pill, ScoreBadge, Skeleton, StatusBadge, cn } from "@/components/ui";
import CastChip from "@/components/workspace/CastChip";
import CostMeter from "@/components/workspace/CostMeter";
import {
  aspectClass,
  cameraLine,
  chosenTake,
  isPlayable,
  isRendered,
  isRunning,
} from "@/components/workspace/shared";

export default function ShotBoard({
  shots,
  scenes,
  versions,
  characters,
  aspect,
  busy,
  generating,
  batchBusy,
  produce,
  projectId,
  budgetUsd,
  scopedShotIds,
  scopedCastIds,
  highlightedShotIds,
  onOpen,
  onGenerate,
  onKeyframes,
  onRenderAll,
  onProduce,
  onStopProduce,
  onToggleShotScope,
  onToggleCastScope,
  onAttachCast,
}: {
  shots: Shot[];
  scenes: Scene[];
  versions: Record<string, ShotVersion[]>;
  characters: Character[];
  aspect: string;
  busy: Record<string, boolean>;
  generating: string[];
  batchBusy: string | null;
  produce: ProduceStatus | null;
  projectId: string;
  budgetUsd?: number | null;
  scopedShotIds: string[];
  scopedCastIds: string[];
  highlightedShotIds: string[];
  onOpen: (shotId: string) => void;
  onGenerate: (shotId: string) => void;
  onKeyframes: () => void;
  onRenderAll: (chained: boolean) => void;
  onProduce: () => void;
  onStopProduce: () => void;
  onToggleShotScope: (shotId: string) => void;
  onToggleCastScope: (castId: string) => void;
  onAttachCast: (shotId: string, castId: string) => void;
}) {
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  if (shots.length === 0) {
    return (
      <EmptyState
        title="No storyboard yet"
        hint="Plan the production first — the storyboard agent breaks the script into an executable shot list with camera, performance, and acceptance rules."
      />
    );
  }
  const withKeyframe = shots.filter((s) => s.keyframe_frame_id).length;
  const staleCount = shots.filter((s) => s.stale).length;
  const renderedCount = shots.filter((s) => isRendered(versions[s.id] ?? [])).length;
  const runningCount = shots.filter(
    (s) => (versions[s.id] ?? []).some(isRunning) || generating.includes(s.id),
  ).length;
  const reviseCount = shots.filter((s) => s.keyframe_verdict === "revise").length;
  // group shots into scene bands; scene metadata joins by order (fallback to bare "Sn")
  const sceneByOrder = new Map(scenes.map((s) => [s.order, s]));
  const sceneOrders = [...new Set(shots.map((s) => s.scene_order))].sort((a, b) => a - b);
  return (
    <div>
      {/* batch toolbar — keyframes are image-priced; chained render queues on upstream takes */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {/* one-click Produce: runs every remaining stage; pauses after fresh keyframes for review */}
        {produce?.running ? (
          <Button onClick={onStopProduce} title="Stop the produce run (finished work is kept)">
            <Square size={14} aria-hidden /> Stop
          </Button>
        ) : (
          <Button
            onClick={onProduce}
            disabled={!!batchBusy}
            title={
              produce?.state === "paused"
                ? "Resume: continues from where the run paused"
                : "Run everything that's missing — portraits, keyframes (pause for review), videos, voiceovers, rough cut"
            }
          >
            <Clapperboard size={14} aria-hidden />
            {produce?.state === "paused" ? "Continue produce" : "Produce"}
          </Button>
        )}
        <Button
          onClick={onKeyframes}
          loading={batchBusy === "keyframes"}
          disabled={!!batchBusy || withKeyframe === shots.length}
          title="Generate every missing shot keyframe as an image — approve composition before spending video budget"
        >
          <ImageIcon size={14} aria-hidden />
          Keyframes {withKeyframe}/{shots.length}
        </Button>
        <Button
          onClick={() => onRenderAll(false)}
          loading={batchBusy === "render"}
          disabled={!!batchBusy}
          title="Render every shot — keyframed shots submit in parallel"
        >
          <Film size={14} aria-hidden /> Render all
        </Button>
        <Button
          onClick={() => onRenderAll(true)}
          loading={batchBusy === "render-chained"}
          disabled={!!batchBusy}
          title="Render in a continuation chain — each shot seeds from the previous take's last frame"
        >
          <Link2 size={14} aria-hidden /> Render chained
        </Button>
        <CostMeter projectId={projectId} budgetUsd={budgetUsd} refreshKey={shots.length} />
        {staleCount > 0 && (
          <Pill className="text-accent">{staleCount} stale — replanning recommended</Pill>
        )}
        {produce && produce.state !== "idle" && produce.state !== "stopped" && (
          <Pill className={produce.state === "error" ? "text-accent" : produce.running ? "text-run" : undefined}>
            {produce.running && <span className="mr-1 inline-block size-1.5 rounded-full bg-run pulse-dot" aria-hidden />}
            produce · {produce.stage ?? produce.state}
            {produce.detail ? ` — ${produce.detail}` : ""}
          </Pill>
        )}
      </div>
      {/* live production counts — the board reads as a crew dashboard, not a static gallery */}
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.7rem] text-faint">
        <span>
          {withKeyframe}/{shots.length} keyframed
        </span>
        <span aria-hidden>·</span>
        <span>
          {renderedCount}/{shots.length} rendered
        </span>
        {runningCount > 0 && (
          <span className="inline-flex items-center gap-1 text-run">
            <span className="size-1.5 rounded-full bg-run pulse-dot" aria-hidden />
            {runningCount} running
          </span>
        )}
        {reviseCount > 0 && (
          <span className="text-accent">
            {reviseCount} keyframe{reviseCount === 1 ? "" : "s"} to revise
          </span>
        )}
      </div>
      {characters.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Eyebrow>Cast</Eyebrow>
          {characters.map((c) => (
            <CastChip
              key={c.id}
              character={c}
              selected={scopedCastIds.includes(c.id)}
              onToggle={() => onToggleCastScope(c.id)}
            />
          ))}
          <span className="text-[0.7rem] text-faint">
            Click a cast member to direct with them (adds @{"{name}"} to the director).
          </span>
        </div>
      )}
      <div className="space-y-8">
        {sceneOrders.map((so) => {
          const scene = sceneByOrder.get(so);
          const sceneShots = shots.filter((s) => s.scene_order === so);
          const rendered = sceneShots.filter((s) => isRendered(versions[s.id] ?? [])).length;
          const dur = sceneShots.reduce(
            (acc, s) => acc + (chosenTake(versions[s.id] ?? [])?.duration_sec ?? s.duration_sec),
            0,
          );
          const sceneStale = scene?.stale || sceneShots.some((s) => s.stale);
          return (
            <section key={so} aria-label={`Scene ${so + 1}`}>
              <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border pb-2">
                <span className="eyebrow text-accent">S{so + 1}</span>
                {scene?.title && <h3 className="title text-lg text-fg">{scene.title}</h3>}
                <span className="font-mono text-[0.7rem] text-faint">
                  {sceneShots.length} shot{sceneShots.length === 1 ? "" : "s"} · ~{dur.toFixed(1)}s ·{" "}
                  {rendered}/{sceneShots.length} rendered
                </span>
                {sceneStale && <Pill className="text-accent">stale</Pill>}
              </header>
              {/* horizontal filmstrip — the storyboard reads as a sequence, not a gallery */}
              <div className="flex snap-x gap-4 overflow-x-auto pb-3">
                {sceneShots.map((shot, i) => (
                  <div
                    key={shot.id}
                    onDragOver={(e) => {
                      if (e.dataTransfer.types.includes("application/x-extrovid-cast")) {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "copy";
                        setDragOverId(shot.id);
                      }
                    }}
                    onDragLeave={() => setDragOverId((id) => (id === shot.id ? null : id))}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOverId(null);
                      const castId = e.dataTransfer.getData("application/x-extrovid-cast");
                      if (castId) onAttachCast(shot.id, castId);
                    }}
                    className={cn(
                      "w-44 shrink-0 snap-start rounded-[var(--radius)] sm:w-52",
                      dragOverId === shot.id && "ring-2 ring-accent ring-offset-2 ring-offset-bg",
                    )}
                  >
                    <ShotCard
                      shot={shot}
                      versions={versions[shot.id] ?? []}
                      aspect={aspect}
                      busy={!!busy[shot.id] || generating.includes(shot.id)}
                      selected={scopedShotIds.includes(shot.id)}
                      highlighted={highlightedShotIds.includes(shot.id)}
                      cast={characters.find((c) => c.id === shot.character_id) ?? null}
                      onOpen={() => onOpen(shot.id)}
                      onGenerate={() => onGenerate(shot.id)}
                      onToggleScope={() => onToggleShotScope(shot.id)}
                      delay={i * 40}
                    />
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ShotCard({
  shot,
  versions,
  aspect,
  busy,
  selected,
  highlighted,
  cast,
  onOpen,
  onGenerate,
  onToggleScope,
  delay,
}: {
  shot: Shot;
  versions: ShotVersion[];
  aspect: string;
  busy: boolean;
  selected: boolean;
  highlighted: boolean;
  cast: Character | null;
  onOpen: () => void;
  onGenerate: () => void;
  onToggleScope: () => void;
  delay: number;
}) {
  const take = chosenTake(versions);
  const jobRunning = busy || versions.some(isRunning);
  const failed = !take && !jobRunning && versions.some((v) => v.job_status === "failed");
  const model = (take?.model ?? shot.preferred_model).split(":").pop()!.replace("wan2.7-", "");
  const thumb = take && isPlayable(take.thumbnail_url) ? take.thumbnail_url : null;
  const finishedCount = versions.filter((v) => v.output_asset_id).length;

  return (
    <Panel
      selected={selected && !highlighted}
      className={cn("rise overflow-hidden", highlighted && "ring-2 ring-live")}
      style={{ animationDelay: `${delay}ms` }}
    >
      <button
        onClick={(e) => {
          // ⌘/Ctrl/Shift-click scopes the director to this shot; a plain click opens the inspector
          if (e.metaKey || e.ctrlKey || e.shiftKey) {
            e.preventDefault();
            onToggleScope();
          } else {
            onOpen();
          }
        }}
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
          <span className="relative flex size-full flex-col items-center justify-center gap-2 p-3 text-center">
            {jobRunning ? (
              <>
                <Skeleton className="absolute inset-0 rounded-none" />
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
        {(shot.stale || shot.keyframe_frame_id) && (
          <span className="absolute left-2 top-9 flex flex-col items-start gap-1">
            {shot.stale && (
              <span
                title="An upstream artifact changed after this shot was planned"
                className="rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.6rem] text-accent backdrop-blur"
              >
                stale
              </span>
            )}
            {shot.keyframe_frame_id && (
              <span
                title="Has a planned keyframe — generation anchors on it"
                className="rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.6rem] text-ok backdrop-blur"
              >
                KF
              </span>
            )}
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
        {cast && (
          <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-border-hi bg-bg-soft px-1.5 py-0.5 text-[0.65rem] text-muted">
            <span className="size-3.5 shrink-0 overflow-hidden rounded-full bg-panel">
              {isPlayable(cast.reference_image_urls[0]) && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={cast.reference_image_urls[0]} alt="" className="size-full object-cover" />
              )}
            </span>
            {cast.name}
          </span>
        )}
        <StageStrip shot={shot} jobRunning={jobRunning} failed={failed} take={take} />
        <button
          type="button"
          onClick={onToggleScope}
          aria-pressed={selected}
          title={selected ? "Remove from director scope" : "Direct this shot — adds @shot to the director"}
          className={cn(
            "mt-3 inline-flex items-center gap-1 rounded-[var(--radius)] px-1.5 py-1 font-mono text-[0.65rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            selected ? "text-accent" : "text-faint hover:text-fg",
          )}
        >
          ◎ {selected ? "directing" : "direct"}
        </button>
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

const STAGE_DOT: Record<string, string> = {
  ok: "bg-ok",
  run: "bg-run pulse-dot",
  warn: "bg-accent",
  fail: "bg-fail",
  off: "bg-border-hi",
};
const STAGE_TEXT: Record<string, string> = {
  ok: "text-ok",
  run: "text-run",
  warn: "text-accent",
  fail: "text-fail",
  off: "text-faint",
};

/** Per-shot pipeline rail: keyframe (gate) → render → review, color-coded by state. */
function StageStrip({
  shot,
  jobRunning,
  failed,
  take,
}: {
  shot: Shot;
  jobRunning: boolean;
  failed: boolean;
  take?: ShotVersion;
}) {
  const kfTone = !shot.keyframe_frame_id
    ? "off"
    : shot.keyframe_verdict === "revise"
      ? "warn"
      : "ok";
  const renderTone = jobRunning ? "run" : failed ? "fail" : take ? "ok" : "off";
  const reviewTone = !take?.review ? "off" : take.review.verdict === "revise" ? "fail" : "ok";
  const stages = [
    {
      key: "kf",
      tone: kfTone,
      text: "kf",
      title: `keyframe — ${shot.keyframe_frame_id ? (shot.keyframe_verdict ?? "set") : "not generated"}`,
    },
    {
      key: "render",
      tone: renderTone,
      text: "render",
      title: `render — ${jobRunning ? "running" : failed ? "failed" : take ? "rendered" : "not generated"}`,
    },
    {
      key: "review",
      tone: reviewTone,
      text: take?.score != null ? `★${take.score.toFixed(1)}` : "review",
      title: `review — ${take?.review?.verdict ?? "not reviewed"}`,
    },
  ];
  return (
    <div className="mt-3 flex items-center gap-1.5" aria-label="shot pipeline status">
      {stages.map((s, i) => (
        <Fragment key={s.key}>
          {i > 0 && <span className="h-px flex-1 bg-border" aria-hidden />}
          <span className="inline-flex items-center gap-1 font-mono text-[0.6rem]" title={s.title}>
            <span className={cn("size-1.5 rounded-full", STAGE_DOT[s.tone])} aria-hidden />
            <span className={STAGE_TEXT[s.tone]}>{s.text}</span>
          </span>
        </Fragment>
      ))}
    </div>
  );
}
