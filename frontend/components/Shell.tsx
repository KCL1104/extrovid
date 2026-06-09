"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";

// Two-pane app layout. Desktop (lg+) keeps the sidebar as a permanent left rail;
// on smaller screens it collapses into a slide-in drawer opened from a sticky top bar.
export default function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close the drawer whenever navigation lands on a new route.
  useEffect(() => setOpen(false), [pathname]);

  // While the drawer is open, lock background scroll and let Escape close it.
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="min-h-screen lg:flex">
      {/* mobile top bar (hidden once the permanent sidebar shows at lg) */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-bg/80 px-4 py-3 backdrop-blur lg:hidden">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          className="-ml-2 inline-flex size-10 items-center justify-center rounded-[var(--radius)] text-fg transition-colors hover:bg-panel-hi"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>
        <Link href="/" className="title text-xl text-fg">
          extro<span className="italic text-accent">vid</span>
        </Link>
      </header>

      {/* drawer backdrop (mobile only) */}
      {open && (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
        />
      )}

      <Sidebar open={open} onClose={() => setOpen(false)} />

      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
