"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createProject, listProjects, type Project } from "@/lib/api";
import { cn } from "@/components/ui";
import { PROJECTS_CHANGED } from "@/components/Sidebar";

type Cmd = { id: string; label: string; hint?: string; run: () => void };

/** Keyboard-first command spine (⌘K / Ctrl-K): jump between projects, create one, or navigate.
 *  Mounted once in the app shell; in-workspace stage nav stays on the number keys. */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setQ("");
        setActive(0);
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    listProjects()
      .then(setProjects)
      .catch(() => {});
    const t = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  const close = () => {
    setQ("");
    setActive(0);
    setOpen(false);
  };

  async function newProject() {
    close();
    try {
      const p = await createProject();
      window.dispatchEvent(new Event(PROJECTS_CHANGED));
      router.push(`/projects/${p.id}`);
    } catch {
      /* surfaced on the dashboard if it fails */
    }
  }

  const cmds: Cmd[] = [
    { id: "new", label: "New project", hint: "create", run: newProject },
    { id: "dash", label: "Dashboard", hint: "go", run: () => { close(); router.push("/"); } },
    { id: "gallery", label: "Gallery", hint: "go", run: () => { close(); router.push("/gallery"); } },
    ...projects.map((p) => ({
      id: `p-${p.id}`,
      label: p.title,
      hint: "open project",
      run: () => {
        close();
        router.push(`/projects/${p.id}`);
      },
    })),
  ];
  const filtered = q.trim()
    ? cmds.filter((c) => c.label.toLowerCase().includes(q.trim().toLowerCase()))
    : cmds;
  const sel = Math.min(active, Math.max(0, filtered.length - 1));

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/60 p-4 pt-[15vh] backdrop-blur-sm"
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-[var(--radius)] bg-elevated ring-1 ring-border-hi"
      >
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              filtered[sel]?.run();
            } else if (e.key === "Escape") {
              close();
            }
          }}
          placeholder="Jump to a project, or type a command…"
          aria-label="Command palette search"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm text-fg outline-none placeholder:text-faint"
        />
        <ul className="max-h-80 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <li className="px-4 py-3 text-sm text-faint">No matches</li>
          ) : (
            filtered.map((c, i) => (
              <li key={c.id}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => c.run()}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors",
                    i === sel ? "bg-panel-hi text-fg" : "text-muted hover:bg-panel-hi/60",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate">{c.label}</span>
                  {c.hint && <span className="shrink-0 font-mono text-[0.6rem] text-faint">{c.hint}</span>}
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center gap-3 border-t border-border px-4 py-2 font-mono text-[0.6rem] text-faint">
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-border-hi bg-bg-soft px-1 text-fg">↑↓</kbd> navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-border-hi bg-bg-soft px-1 text-fg">⏎</kbd> open
          </span>
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-border-hi bg-bg-soft px-1 text-fg">esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
