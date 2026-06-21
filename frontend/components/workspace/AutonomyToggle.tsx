"use client";

import { useState } from "react";
import { updateProject } from "@/lib/api";
import { cn } from "@/components/ui";

/** Direction autonomy — Co-direct (pause at the review gate before spending) vs Auto-direct
 *  (run straight through, review at the end). Backed by project.autonomy; the budget ceiling
 *  is enforced in both modes. Optimistic, reverts on failure. */
export default function AutonomyToggle({
  projectId,
  value,
  onChange,
}: {
  projectId: string;
  value: "co" | "auto";
  onChange: (v: "co" | "auto") => void;
}) {
  const [busy, setBusy] = useState(false);
  async function set(v: "co" | "auto") {
    if (v === value || busy) return;
    setBusy(true);
    onChange(v); // optimistic
    try {
      await updateProject(projectId, { autonomy: v });
    } catch {
      onChange(value); // revert
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      role="group"
      aria-label="Direction autonomy"
      className="inline-flex rounded-[var(--radius)] border border-border bg-bg-soft p-0.5 font-mono text-[0.7rem]"
    >
      {(
        [
          ["co", "Co-direct"],
          ["auto", "Auto-direct"],
        ] as const
      ).map(([v, label]) => (
        <button
          key={v}
          type="button"
          onClick={() => set(v)}
          aria-pressed={value === v}
          disabled={busy}
          title={
            v === "co"
              ? "Pause at the review gate before spending"
              : "Run straight through — review at the end (budget still enforced)"
          }
          className={cn(
            "rounded-[calc(var(--radius)-0.2rem)] px-2.5 py-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60",
            value === v ? "bg-panel-hi text-accent" : "text-muted hover:text-fg",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
