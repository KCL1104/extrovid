"use client";

import { useEffect, useState } from "react";
import { getPlanCost, type PlanCost } from "@/lib/api";
import { cn } from "@/components/ui";

/** Pre-spend cost transparency — the projected cost to render the full plan once, against the
 *  approved budget, shown at the spend moment (the batch toolbar). Reds out when over budget. */
export default function CostMeter({
  projectId,
  budgetUsd,
  refreshKey,
}: {
  projectId: string;
  budgetUsd?: number | null;
  refreshKey?: number;
}) {
  const [cost, setCost] = useState<PlanCost | null>(null);
  useEffect(() => {
    let live = true;
    getPlanCost(projectId)
      .then((c) => live && setCost(c))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [projectId, refreshKey]);

  if (!cost) return null;
  const over = budgetUsd != null && cost.total_usd > budgetUsd;
  return (
    <span
      title={
        over
          ? "Projected render cost exceeds the approved budget"
          : "Projected cost to render the full plan once"
      }
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-mono text-[0.7rem]",
        over ? "border-fail/40 bg-fail/10 text-fail" : "border-border-hi bg-bg-soft text-muted",
      )}
    >
      ≈ ${cost.total_usd.toFixed(2)}
      {budgetUsd != null && <span className="text-faint">/ ${budgetUsd.toFixed(2)}</span>}
    </span>
  );
}
