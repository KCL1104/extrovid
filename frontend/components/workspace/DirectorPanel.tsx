"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import {
  directorTurns,
  type DirectorAction,
  type DirectorTurn,
  type ProjectState,
} from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import { Button, Eyebrow, Panel, Pill } from "@/components/ui";
import AgentMessage from "@/components/workspace/AgentMessage";
import StepTrace, { type TraceStep } from "@/components/workspace/StepTrace";
import { errMsg, usageChanged } from "@/components/workspace/shared";

type ChatItem = DirectorTurn & { actions?: DirectorAction[] };

const SUGGESTIONS = [
  "Where are we? What should I do next?",
  "Make scene 1 moodier and mark what needs replanning.",
  "Render every shot of scene 0.",
  "Review the takes — anything drifting between shots?",
];

export default function DirectorPanel({
  projectId,
  onChanged,
  scopeChips = [],
  onRemoveChip,
  onClearScope,
}: {
  projectId: string;
  onChanged: () => Promise<void> | void;
  scopeChips?: { key: string; label: string; ref: string }[];
  onRemoveChip?: (key: string) => void;
  onClearScope?: () => void;
}) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [liveSteps, setLiveSteps] = useState<TraceStep[]>([]);
  const [streamReply, setStreamReply] = useState(""); // the reply as it streams in, token by token
  const [state, setState] = useState<ProjectState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    directorTurns(projectId)
      .then(setItems)
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length, sending, liveSteps.length, streamReply.length]);

  async function send(text?: string) {
    const raw = (text ?? message).trim();
    if (!raw || sending) return;
    // scope chips (selected shots / cast) ride into the instruction as a natural-language prefix
    const prefix = scopeChips.length
      ? `Regarding ${scopeChips.map((c) => c.ref).join(", ")}: `
      : "";
    const content = prefix + raw;
    setMessage("");
    setError(null);
    setSending(true);
    setLiveSteps([]);
    setStreamReply("");
    onClearScope?.();
    setItems((xs) => [
      ...xs,
      { id: `local-${Date.now()}`, role: "user", content, created_at: "" },
    ]);
    try {
      // stream the turn: tool calls arrive as live trace steps, the reply streams token by token
      await streamSSE(`/projects/${projectId}/director/stream`, {
        method: "POST",
        body: { message: content },
        onEvent: (e) => {
          if (e.type === "tool_start" && typeof e.tool === "string") {
            const tool = e.tool;
            setLiveSteps((s) => [...s, { id: `${tool}-${s.length}`, tool, status: "running" }]);
          } else if (e.type === "tool_result" && typeof e.tool === "string") {
            const tool = e.tool;
            const isErr = e.error === true;
            // resolve the most recent still-running step for this tool
            setLiveSteps((steps) => {
              for (let i = steps.length - 1; i >= 0; i--) {
                if (steps[i].tool === tool && steps[i].status === "running") {
                  const next = steps.slice();
                  next[i] = { ...next[i], status: isErr ? "error" : "done" };
                  return next;
                }
              }
              return steps;
            });
          } else if (e.type === "text_delta") {
            const delta = typeof e.delta === "string" ? e.delta : "";
            if (delta) setStreamReply((r) => r + delta);
          } else if (e.type === "error") {
            setError(String(e.message ?? "stream error"));
          } else if (e.type === "done") {
            const actions = (e.actions as DirectorAction[]) ?? [];
            setItems((xs) => [
              ...xs,
              {
                id: `local-${Date.now()}-a`,
                role: "assistant",
                content: String(e.reply ?? ""),
                created_at: "",
                actions,
              },
            ]);
            setState((e.state as ProjectState) ?? null);
            if (actions.length) {
              usageChanged();
              void onChanged(); // tools may have planned/revised/generated — refresh
            }
          }
        },
      });
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSending(false);
      setLiveSteps([]);
      setStreamReply("");
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Eyebrow>Director</Eyebrow>
          <p className="mt-1 text-xs leading-relaxed text-faint">
            One conversation that runs the production — it plans, revises (marking stale work
            instead of destroying it), renders, and reads reviews through tools.
          </p>
        </div>
        {state && (
          <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
            <Pill>{state.shots} shots</Pill>
            <Pill>{state.shots_with_take} rendered</Pill>
            {state.stale_shots > 0 && <Pill className="text-accent">{state.stale_shots} stale</Pill>}
            {state.jobs_in_flight > 0 && (
              <Pill className="text-run">{state.jobs_in_flight} in flight</Pill>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {items.length === 0 && !sending && (
          <Panel className="p-4">
            <p className="text-sm text-muted">
              Ask anything about the production — or hand over a task:
            </p>
            <div className="mt-3 flex flex-col gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-left font-mono text-[0.75rem] text-muted transition-colors hover:border-accent/40 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {s}
                </button>
              ))}
            </div>
          </Panel>
        )}
        {items.map((t) => (
          <AgentMessage key={t.id} turn={t} actions={t.actions} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="w-full max-w-[85%] space-y-2">
              {liveSteps.length > 0 && <StepTrace steps={liveSteps} />}
              {streamReply ? (
                <div className="rounded-[var(--radius)] border border-border bg-panel px-3.5 py-2.5 text-sm leading-relaxed text-muted">
                  <p className="whitespace-pre-wrap">
                    {streamReply}
                    <span
                      className="ml-0.5 inline-block animate-pulse font-mono text-live"
                      aria-hidden
                    >
                      ▍
                    </span>
                  </p>
                </div>
              ) : (
                liveSteps.length === 0 && <StepTrace steps={[]} />
              )}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="mt-2 font-mono text-[0.75rem] text-fail">{error}</p>}

      {scopeChips.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {scopeChips.map((c) => (
            <span
              key={c.key}
              className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[0.65rem] text-accent"
            >
              {c.label}
              <button
                type="button"
                onClick={() => onRemoveChip?.(c.key)}
                aria-label={`Remove ${c.label}`}
                className="text-accent/70 transition-colors hover:text-accent"
              >
                ×
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={() => onClearScope?.()}
            className="font-mono text-[0.6rem] text-faint transition-colors hover:text-fg"
          >
            clear
          </button>
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <label className="sr-only" htmlFor="director-chat-input">
          Message the director
        </label>
        <input
          id="director-chat-input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={sending}
          placeholder="“make scene 2 moodier and redo its shots” — the director acts via tools"
          className="min-w-0 flex-1 rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2.5 font-mono text-xs text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        />
        <Button variant="primary" onClick={() => send()} disabled={!message.trim() || sending}>
          <Send size={14} aria-hidden /> Send
        </Button>
      </div>
    </div>
  );
}
