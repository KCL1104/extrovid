"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import type { Job } from "@/lib/api";
import { EmptyState, Eyebrow, Panel, Pill, StatusBadge, cn } from "@/components/ui";
import { relTime } from "@/components/workspace/shared";

export default function QueuePanel({
  jobs,
  onRetry,
}: {
  jobs: Job[];
  onRetry: (jobId: string) => Promise<void>;
}) {
  const [retrying, setRetrying] = useState<string | null>(null);

  if (jobs.length === 0) {
    return (
      <EmptyState
        title="Queue is empty"
        hint="Every shot generation, revision, and retake lands here with its status, model, and cost."
      />
    );
  }

  const running = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
  const failed = jobs.filter((j) => j.status === "failed").length;
  const spend = jobs.reduce((acc, j) => acc + (j.cost_usd || 0), 0);

  async function retry(id: string) {
    setRetrying(id);
    try {
      await onRetry(id);
    } finally {
      setRetrying(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Eyebrow>Generation queue</Eyebrow>
        <Pill>{jobs.length} jobs</Pill>
        {running > 0 && <Pill className="text-run">{running} running</Pill>}
        {failed > 0 && <Pill className="text-fail">{failed} failed</Pill>}
        <Pill className="text-accent">≈ ${spend.toFixed(2)}</Pill>
      </div>
      <Panel className="rise divide-y divide-border overflow-hidden">
        {jobs.map((j) => (
          <div key={j.id} className="flex items-center gap-3 px-4 py-3">
            <span className="h-12 w-9 shrink-0 overflow-hidden rounded bg-bg-soft">
              {j.thumbnail_url?.startsWith("http") && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={j.thumbnail_url} alt="" className="size-full object-cover" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-fg">
                <span className="mr-1.5 font-mono text-[0.7rem] text-accent">
                  #{j.shot_order + 1}
                </span>
                {j.shot_purpose}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[0.65rem] text-faint">
                {j.model && <span>{j.model.split(":").pop()}</span>}
                <span>{relTime(j.started_at)}</span>
                {j.cost_usd > 0 && <span>${j.cost_usd.toFixed(2)}</span>}
                {j.failure_reason && (
                  <span className="text-fail" title={j.failure_reason}>
                    {j.failure_reason.slice(0, 60)}
                  </span>
                )}
              </p>
            </div>
            <StatusBadge status={j.status} />
            {j.status === "failed" && (
              <button
                onClick={() => retry(j.id)}
                disabled={retrying === j.id}
                className={cn(
                  "inline-flex min-h-10 items-center gap-1.5 rounded-[var(--radius)] border border-border px-2.5 font-mono text-[0.7rem] text-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                )}
              >
                <RefreshCw size={12} className={retrying === j.id ? "animate-spin" : ""} aria-hidden />
                retry
              </button>
            )}
          </div>
        ))}
      </Panel>
    </div>
  );
}
