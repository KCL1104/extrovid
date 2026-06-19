"use client";

import { useState } from "react";
import { getUser } from "@/lib/auth";
import SettingsModal from "@/components/SettingsModal";

// Sidebar footer: the user's email opens the Settings modal (account · usage · security · danger).
export default function AccountMenu() {
  const user = getUser();
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-border px-3 py-3">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="Settings"
        className="flex w-full items-center justify-between gap-2 rounded-[var(--radius)] px-1 py-1 text-left transition-colors hover:bg-panel-hi"
      >
        <span className="min-w-0">
          <span className="block truncate text-xs text-fg">{user?.email ?? "Account"}</span>
          <span className="text-[0.65rem] text-faint">
            {user?.is_admin ? "admin · " : ""}settings &amp; usage
          </span>
        </span>
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0 text-faint"
          aria-hidden
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {open && <SettingsModal onClose={() => setOpen(false)} />}
    </div>
  );
}
