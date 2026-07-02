"use client";

import { Fragment } from "react";
import type { Scene, Shot, ShotVersion } from "@/lib/api";
import { cn } from "@/components/ui";
import { chosenTake, isPlayable, isRendered, isRunning } from "@/components/workspace/shared";

/** Sequence altitude — the same shots as the board, read as a low-density timeline: block width
 *  encodes duration (pacing is visible), and an arrow between adjacent shots greens up once both
 *  are rendered (continuity established / the baton can chain). Click to inspect; ⌘-click to direct. */
export default function TimelineStrip({
  shots,
  scenes,
  versions,
  scopedShotIds,
  onOpen,
  onToggleShotScope,
}: {
  shots: Shot[];
  scenes: Scene[];
  versions: Record<string, ShotVersion[]>;
  scopedShotIds: string[];
  onOpen: (shotId: string) => void;
  onToggleShotScope: (shotId: string) => void;
}) {
  const sceneByOrder = new Map(scenes.map((s) => [s.order, s]));
  const sceneOrders = [...new Set(shots.map((s) => s.scene_order))].sort((a, b) => a - b);

  return (
    <div className="space-y-6">
      <p className="font-mono text-[0.7rem] text-faint">
        Block width = duration · an arrow greens up when the next shot can continue from this one’s
        last frame.
      </p>
      {sceneOrders.map((so) => {
        const scene = sceneByOrder.get(so);
        const sceneShots = shots
          .filter((s) => s.scene_order === so)
          .sort((a, b) => a.order - b.order);
        return (
          <section key={so} aria-label={`Scene ${so + 1}`}>
            <header className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="eyebrow text-accent">S{so + 1}</span>
              {scene?.title && <h3 className="title text-base text-fg">{scene.title}</h3>}
            </header>
            <div className="flex items-stretch overflow-x-auto pb-2">
              {sceneShots.map((shot, i) => {
                const vs = versions[shot.id] ?? [];
                const take = chosenTake(vs);
                const rendered = isRendered(vs);
                const running = vs.some(isRunning);
                const dur = take?.duration_sec ?? shot.duration_sec;
                const selected = scopedShotIds.includes(shot.id);
                const prev = sceneShots[i - 1];
                const prevRendered = prev ? isRendered(versions[prev.id] ?? []) : false;
                const thumb =
                  (take && isPlayable(take.thumbnail_url) ? take.thumbnail_url : null) ??
                  (isPlayable(shot.keyframe_url) ? shot.keyframe_url : null);
                const tone = running
                  ? "border-live/60 bg-live/5"
                  : rendered
                    ? "border-ok/40 bg-ok/5"
                    : "border-border bg-panel";
                return (
                  <Fragment key={shot.id}>
                    {i > 0 && (
                      <span
                        aria-hidden
                        className={cn(
                          "shrink-0 self-center px-0.5 font-mono text-xs",
                          prevRendered && rendered ? "text-ok" : "text-faint",
                        )}
                      >
                        →
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        if (e.metaKey || e.ctrlKey || e.shiftKey) {
                          e.preventDefault();
                          onToggleShotScope(shot.id);
                        } else {
                          onOpen(shot.id);
                        }
                      }}
                      style={{ flexGrow: Math.max(0.5, dur), flexBasis: 0 }}
                      title={`${shot.purpose} — open; ⌘-click to direct`}
                      className={cn(
                        "flex min-w-[5.5rem] flex-col gap-1 rounded-[var(--radius)] border p-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                        tone,
                        selected && "ring-1 ring-accent/40",
                      )}
                    >
                      <div className="flex items-center justify-between font-mono text-[0.65rem]">
                        <span className="text-fg">#{shot.order + 1}</span>
                        <span className="text-faint">{dur.toFixed(1)}s</span>
                      </div>
                      <div className="aspect-video w-full overflow-hidden rounded bg-bg-soft">
                        {thumb && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={thumb}
                            alt=""
                            className="size-full object-cover"
                            onError={(e) => (e.currentTarget.style.visibility = "hidden")}
                          />
                        )}
                      </div>
                      <p className="truncate text-[0.7rem] text-muted">{shot.purpose}</p>
                    </button>
                  </Fragment>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
