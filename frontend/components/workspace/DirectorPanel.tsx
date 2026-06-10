"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Wrench } from "lucide-react";
import {
  directorChat,
  directorTurns,
  type DirectorAction,
  type DirectorTurn,
  type ProjectState,
} from "@/lib/api";
import { Button, Eyebrow, Panel, Pill, Spinner, cn } from "@/components/ui";
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
}: {
  projectId: string;
  onChanged: () => Promise<void> | void;
}) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
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
  }, [items.length, sending]);

  async function send(text?: string) {
    const content = (text ?? message).trim();
    if (!content || sending) return;
    setMessage("");
    setError(null);
    setSending(true);
    setItems((xs) => [
      ...xs,
      { id: `local-${Date.now()}`, role: "user", content, created_at: "" },
    ]);
    try {
      const res = await directorChat(projectId, content);
      setItems((xs) => [
        ...xs,
        {
          id: `local-${Date.now()}-a`,
          role: "assistant",
          content: res.reply,
          created_at: "",
          actions: res.actions,
        },
      ]);
      setState(res.state);
      if (res.actions.length) {
        usageChanged();
        await onChanged(); // tools may have planned/revised/generated — refresh the workspace
      }
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-16rem)] max-w-3xl flex-col">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Eyebrow>Director</Eyebrow>
          <p className="mt-1 text-xs leading-relaxed text-faint">
            One conversation that runs the production — it plans, revises (marking stale
            work instead of destroying it), renders, and reads reviews through tools.
          </p>
        </div>
        {state && (
          <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
            <Pill>{state.shots} shots</Pill>
            <Pill>{state.shots_with_take} rendered</Pill>
            {state.stale_shots > 0 && <Pill className="text-run">{state.stale_shots} stale</Pill>}
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
          <div key={t.id} className={cn("flex", t.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-[var(--radius)] border px-3.5 py-2.5 text-sm leading-relaxed",
                t.role === "user"
                  ? "border-accent/40 bg-accent/10 text-fg"
                  : "border-border bg-panel text-muted",
              )}
            >
              <p className="whitespace-pre-wrap">{t.content}</p>
              {t.actions && t.actions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border pt-2">
                  {t.actions.map((a, i) => (
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
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-[var(--radius)] border border-border bg-panel px-3.5 py-2.5">
              <Spinner className="size-3.5 text-accent" />
              <span className="font-mono text-[0.7rem] text-faint">
                directing — may plan, revise or render…
              </span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="mt-2 font-mono text-[0.75rem] text-fail">{error}</p>}

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
