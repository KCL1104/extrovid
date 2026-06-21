"use client";

import { Wrench } from "lucide-react";
import type { DirectorAction, DirectorTurn } from "@/lib/api";
import { cn } from "@/components/ui";

/** A single director chat bubble. The newest reply streams in live (see DirectorPanel);
 *  finalized messages render instantly, with the tool calls they made as a crew-language footer. */
export default function AgentMessage({
  turn,
  actions,
}: {
  turn: DirectorTurn;
  actions?: DirectorAction[];
}) {
  const isUser = turn.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-[var(--radius)] border px-3.5 py-2.5 text-sm leading-relaxed",
          isUser ? "border-accent/40 bg-accent/10 text-fg" : "border-border bg-panel text-muted",
        )}
      >
        <p className="whitespace-pre-wrap">{turn.content}</p>
        {actions && actions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border pt-2">
            {actions.map((a, i) => (
              <span
                key={`${a.tool}-${i}`}
                title={a.result_summary}
                className="inline-flex items-center gap-1 rounded-full border border-border-hi bg-bg-soft px-2 py-0.5 font-mono text-[0.65rem] text-faint"
              >
                <Wrench size={10} aria-hidden className="text-accent" />
                {a.tool}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
