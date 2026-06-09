"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createProject, listProjects, type Project } from "@/lib/api";
import { clearAuth, getUser } from "@/lib/auth";
import { Button, Spinner, cn } from "@/components/ui";

// Fired by the dashboard/sidebar after a project is created or deleted, so both re-fetch.
export const PROJECTS_CHANGED = "extrovid-projects-changed";

// `open`/`onClose` drive the mobile drawer; on lg+ the rail is always visible and ignores them.
export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [creating, setCreating] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const user = getUser();

  useEffect(() => {
    let live = true;
    // transient / unauthorized failures leave the list as-is
    const refresh = () =>
      listProjects()
        .then((p) => live && setProjects(p))
        .catch(() => {});
    refresh();
    window.addEventListener(PROJECTS_CHANGED, refresh);
    return () => {
      live = false;
      window.removeEventListener(PROJECTS_CHANGED, refresh);
    };
  }, []);

  async function newProject() {
    if (creating) return;
    setCreating(true);
    try {
      const p = await createProject();
      window.dispatchEvent(new Event(PROJECTS_CHANGED));
      router.push(`/projects/${p.id}`);
    } catch {
      setCreating(false);
    }
  }

  function signOut() {
    clearAuth();
    window.location.assign("/");
  }

  function navItem(href: string, label: string) {
    const active = href === "/" ? pathname === "/" : pathname?.startsWith(href);
    return (
      <Link
        href={href}
        className={`rounded-[var(--radius)] px-2 py-1.5 text-sm transition-colors ${
          active ? "bg-panel-hi text-fg" : "text-muted hover:bg-panel-hi hover:text-fg"
        }`}
      >
        {label}
      </Link>
    );
  }

  return (
    <aside
      className={cn(
        // mobile: off-canvas fixed drawer that slides in
        "fixed left-0 top-0 z-50 flex h-screen w-64 shrink-0 flex-col border-r border-border bg-bg-soft transition-transform duration-300 ease-out",
        // desktop: permanent sticky rail (translucent, no slide)
        "lg:sticky lg:z-auto lg:translate-x-0 lg:bg-bg-soft/40 lg:transition-none",
        open ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex items-center justify-between px-4 py-5">
        <Link href="/" onClick={onClose} className="title text-2xl text-fg">
          extro<span className="italic text-accent">vid</span>
        </Link>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close menu"
          className="-mr-2 inline-flex size-10 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-fg lg:hidden"
        >
          ✕
        </button>
      </div>

      <div className="px-3">
        <Button
          variant="primary"
          onClick={newProject}
          loading={creating}
          className="w-full justify-center"
        >
          + New project
        </Button>
      </div>

      <nav className="mt-4 flex flex-col gap-1 px-3">
        {navItem("/", "Dashboard")}
        {navItem("/gallery", "Gallery")}
      </nav>

      <p className="eyebrow mt-6 px-4">Projects</p>
      <div className="mt-2 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {projects === null ? (
          <div className="px-1 py-2">
            <Spinner />
          </div>
        ) : projects.length === 0 ? (
          <p className="px-1 py-2 text-xs text-faint">No projects yet</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {projects.map((p) => {
              const active = pathname === `/projects/${p.id}`;
              return (
                <li key={p.id}>
                  <Link
                    href={`/projects/${p.id}`}
                    className={`block truncate rounded-[var(--radius)] px-2 py-1.5 text-sm transition-colors ${
                      active ? "bg-panel-hi text-fg" : "text-muted hover:bg-panel-hi hover:text-fg"
                    }`}
                  >
                    {p.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-border px-4 py-3">
        {user && (
          <p className="truncate text-xs text-faint">
            {user.email}
            {user.is_admin ? " · admin" : ""}
          </p>
        )}
        <button onClick={signOut} className="mt-1 text-xs text-muted transition-colors hover:text-fg">
          Sign out
        </button>
      </div>
    </aside>
  );
}
