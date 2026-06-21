"use client";

import { useState } from "react";
import { ChevronUp } from "lucide-react";
import type { Job } from "@/lib/api";
import { Pill, cn } from "@/components/ui";
import QueuePanel from "@/components/workspace/QueuePanel";

/** Persistent footer status strip — the generation queue as a production HUD, not a tab.
 *  Collapsed by default; expands to the full job list. Sticks to the bottom of the canvas. */
export default function QueueDock({
  jobs,
  onRetry,
}: {
  jobs: Job[];
  onRetry: (jobId: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const running = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
  const failed = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="sticky bottom-0 z-20 border-t border-border bg-bg/90 backdrop-blur">
      {open && (
        <div className="max-h-[50vh] overflow-y-auto border-b border-border px-4 py-4 sm:px-6">
          <QueuePanel jobs={jobs} onRetry={onRetry} />
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-panel-hi/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent sm:px-6"
      >
        <span className="eyebrow">Queue</span>
        <Pill>{jobs.length}</Pill>
        {running > 0 && (
          <span className="inline-flex items-center gap-1.5 font-mono text-[0.7rem] text-run">
            <span className="size-1.5 rounded-full bg-run pulse-dot" aria-hidden />
            {running} running
          </span>
        )}
        {failed > 0 && <Pill className="text-fail">{failed} failed</Pill>}
        {jobs.length === 0 && <span className="font-mono text-[0.7rem] text-faint">idle</span>}
        <ChevronUp
          size={14}
          aria-hidden
          className={cn("ml-auto text-faint transition-transform", open && "rotate-180")}
        />
      </button>
    </div>
  );
}
