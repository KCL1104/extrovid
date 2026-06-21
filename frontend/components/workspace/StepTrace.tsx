"use client";

import { cn } from "@/components/ui";

export type TraceStep = { id: string; tool: string; status: "running" | "done" | "error" };

const DOT: Record<TraceStep["status"], string> = {
  running: "bg-live pulse-dot",
  done: "bg-ok",
  error: "bg-fail",
};

/** Live agent tool-event trace — the director narrating its work in crew language.
 *  A cyan pulse while a tool runs, resolving to a check; replaces the bare "directing…" spinner. */
export default function StepTrace({ steps }: { steps: TraceStep[] }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[var(--radius)] border border-border bg-panel px-3.5 py-3">
      {steps.length === 0 ? (
        <span className="inline-flex items-center gap-2 font-mono text-[0.7rem] text-live">
          <span className="size-1.5 rounded-full bg-live pulse-dot" aria-hidden />
          directing — may plan, revise or render…
        </span>
      ) : (
        steps.map((s) => (
          <span key={s.id} className="inline-flex items-center gap-2 font-mono text-[0.7rem]">
            <span className={cn("size-1.5 shrink-0 rounded-full", DOT[s.status])} aria-hidden />
            <span
              className={cn(
                "min-w-0 flex-1 truncate",
                s.status === "running"
                  ? "text-fg"
                  : s.status === "error"
                    ? "text-fail"
                    : "text-muted",
              )}
            >
              {s.tool.replace(/_/g, " ")}
            </span>
            {s.status === "done" && (
              <span className="shrink-0 text-ok" aria-hidden>
                ✓
              </span>
            )}
            {s.status === "error" && (
              <span className="shrink-0 text-fail" aria-hidden>
                retry
              </span>
            )}
          </span>
        ))
      )}
    </div>
  );
}
