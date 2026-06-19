"use client";

import { useEffect, useRef, useState } from "react";
import { getUsage, type Usage } from "@/lib/api";
import { clearAuth, getUser } from "@/lib/auth";
import { cn } from "@/components/ui";

// Sidebar account footer: the user's email opens a popover with today's usage + sign out.
// Replaces the old top-right UsageBadge — usage lives behind the account menu, SaaS-style.
function UsageRow({ label, n, cap }: { label: string; n: number; cap: number }) {
  const atCap = cap > 0 && n >= cap;
  const pct = cap > 0 ? Math.min(100, Math.round((n / cap) * 100)) : 0;
  return (
    <div className="mt-2 first:mt-0">
      <div className="flex items-center justify-between font-mono text-[0.7rem]">
        <span className="text-faint">{label}</span>
        <span className={atCap ? "text-fail" : "text-muted"}>
          {n}
          {cap > 0 ? `/${cap}` : ""}
        </span>
      </div>
      {cap > 0 && (
        <div className="mt-1 h-1 overflow-hidden rounded-full bg-bg-soft">
          <div
            className={cn("h-full rounded-full transition-all", atCap ? "bg-fail/70" : "bg-accent/60")}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default function AccountMenu() {
  const user = getUser();
  const [open, setOpen] = useState(false);
  const [u, setU] = useState<Usage | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    const refresh = () =>
      getUsage()
        .then((next) => live && setU(next))
        .catch(() => {});
    refresh();
    window.addEventListener("extrovid-usage-changed", refresh);
    return () => {
      live = false;
      window.removeEventListener("extrovid-usage-changed", refresh);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function signOut() {
    clearAuth();
    window.location.assign("/");
  }

  return (
    <div ref={ref} className="relative border-t border-border px-3 py-3">
      {open && (
        <div className="absolute bottom-full left-3 right-3 mb-2 rounded-[var(--radius)] border border-border bg-panel p-3 shadow-2xl">
          <p className="eyebrow mb-2">Usage · today</p>
          {u ? (
            <>
              <UsageRow label="Videos" n={u.videos_today} cap={u.video_cap} />
              <UsageRow label="Images" n={u.images_today} cap={u.image_cap} />
              <UsageRow label="Voiceovers" n={u.audio_today} cap={u.audio_cap} />
              <div className="mt-3 flex items-center justify-between border-t border-border pt-2 font-mono text-[0.7rem]">
                <span className="text-faint">est. spend</span>
                <span className="text-accent">~${u.est_spend_usd.toFixed(2)}</span>
              </div>
              {u.failed_today > 0 && (
                <p className="mt-1 font-mono text-[0.7rem] text-fail">⚠ {u.failed_today} failed today</p>
              )}
            </>
          ) : (
            <p className="font-mono text-[0.7rem] text-faint">loading…</p>
          )}
          <button
            onClick={signOut}
            className="mt-3 w-full rounded-[var(--radius)] border border-border px-2 py-1.5 text-left text-xs text-muted transition-colors hover:border-fail/40 hover:text-fail"
          >
            Sign out
          </button>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Account and usage"
        className="flex w-full items-center justify-between gap-2 rounded-[var(--radius)] px-1 py-1 text-left transition-colors hover:bg-panel-hi"
      >
        <span className="min-w-0">
          <span className="block truncate text-xs text-fg">{user?.email ?? "Account"}</span>
          <span className="text-[0.65rem] text-faint">{user?.is_admin ? "admin · " : ""}usage &amp; account</span>
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn("shrink-0 text-faint transition-transform", open && "rotate-180")}
          aria-hidden
        >
          <path d="m18 15-6-6-6 6" />
        </svg>
      </button>
    </div>
  );
}
