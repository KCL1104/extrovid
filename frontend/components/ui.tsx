"use client";

import {
  Fragment,
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

export function cn(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

// Shared text input — sunken bg-soft field with the standard amber focus ring.
// The single form-field primitive; use it instead of hand-rolled input classes.
export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-sm text-fg outline-none placeholder:text-faint",
        "focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
        className,
      )}
      {...props}
    />
  );
}

export function Button({
  variant = "default",
  size = "md",
  loading,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "default" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-[var(--radius)] font-medium transition-all duration-200 active:scale-[0.98] disabled:opacity-40 disabled:pointer-events-none disabled:active:scale-100 select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg";
  const sizes = { sm: "px-2.5 py-1.5 text-xs", md: "px-3.5 py-2 text-sm" } as const;
  const variants = {
    primary:
      "bg-accent/15 text-accent border border-accent/40 hover:bg-accent hover:text-bg hover:border-accent",
    default: "bg-panel text-fg border border-border hover:border-border-hi hover:bg-panel-hi",
    ghost: "text-muted hover:text-fg hover:bg-panel-hi",
    danger: "text-fail border border-transparent hover:border-fail/40 hover:bg-fail/10",
  } as const;
  return (
    <button className={cn(base, sizes[size], variants[variant], className)} disabled={loading || props.disabled} {...props}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70",
        className,
      )}
    />
  );
}

// Loading placeholder — shimmer sized to the content it stands in for; the AI-native
// alternative to a bare spinner (size it to the final frame, not a generic bar).
export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return <div aria-hidden className={cn("shimmer rounded-[var(--radius)]", className)} style={style} />;
}

export function Panel({
  className,
  children,
  style,
  hover = false,
  selected = false,
}: {
  className?: string;
  children: ReactNode;
  style?: CSSProperties;
  hover?: boolean;
  selected?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border bg-panel/70",
        selected ? "border-accent/60 ring-1 ring-accent/30" : "border-border",
        hover && "transition-colors hover:border-border-hi hover:bg-panel-hi",
        className,
      )}
      style={style}
    >
      {children}
    </div>
  );
}

export function Alert({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-[var(--radius)] border border-fail/40 bg-fail/10 px-3 py-2 font-mono text-sm text-fail"
    >
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-current" />
      <span>{children}</span>
    </div>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("eyebrow", className)}>{children}</p>;
}

export function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border-hi bg-bg-soft px-2 py-0.5 font-mono text-[0.68rem] text-muted",
        className,
      )}
    >
      {children}
    </span>
  );
}

const STATUS_COLOR: Record<string, string> = {
  succeeded: "text-ok",
  ready: "text-ok",
  accepted: "text-ok",
  running: "text-run",
  queued: "text-run",
  generated: "text-ok",
  draft: "text-muted",
  failed: "text-fail",
};

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status] ?? "text-muted";
  const animate = status === "running" || status === "queued";
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-mono text-[0.7rem]", color)}>
      <span className={cn("size-1.5 rounded-full bg-current", animate && "pulse-dot")} />
      {status}
    </span>
  );
}

export function ScoreBadge({ score, verdict }: { score: number; verdict?: string }) {
  const color =
    verdict === "revise" || score < 6 ? "text-fail" : score < 7.5 ? "text-accent" : "text-ok";
  return (
    <span
      className={cn("inline-flex items-center gap-1 font-mono text-[0.7rem]", color)}
      title={verdict ? `AI review: ${verdict}` : "AI review score"}
    >
      <span aria-hidden>★</span>
      {score.toFixed(1)}
    </span>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="group inline-flex min-h-10 items-center gap-2 rounded-[var(--radius)] px-1 py-1 font-mono text-xs text-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <span
        aria-hidden
        className={cn(
          "relative h-4 w-7 rounded-full border transition-colors",
          checked ? "border-accent bg-accent/30" : "border-border-hi bg-bg-soft",
        )}
      >
        <span
          className={cn(
            "absolute top-1/2 size-3 -translate-y-1/2 rounded-full transition-all",
            checked ? "left-3.5 bg-accent" : "left-0.5 bg-faint",
          )}
        />
      </span>
      {label}
    </button>
  );
}

export type TabItem = {
  id: string;
  label: string;
  meta?: ReactNode;
  live?: boolean;
  done?: boolean; // pipeline step has produced output → shows a ✓
  locked?: boolean; // prerequisite unmet → dimmed, not selectable
  divider?: boolean; // render a separator before this tab (utilities vs. pipeline steps)
};

export function Tabs({
  tabs,
  active,
  onSelect,
}: {
  tabs: TabItem[];
  active: string;
  onSelect: (id: string) => void;
}) {
  // arrow-nav and selection skip locked steps
  const open = tabs.filter((t) => !t.locked);
  const move = (dir: 1 | -1) => {
    if (!open.length) return;
    const idx = open.findIndex((t) => t.id === active);
    const next = open[(Math.max(0, idx) + dir + open.length) % open.length];
    if (next) onSelect(next.id);
  };
  return (
    <div
      role="tablist"
      aria-label="Workspace sections"
      // pb-px contains the active-tab underline (absolute -bottom-px); without it overflow-x-auto
      // makes overflow-y compute to `auto` and the 1px overflow turns the nav vertically scrollable
      className="flex gap-1 overflow-x-auto pb-px"
    >
      {tabs.map((t) => {
        const on = t.id === active;
        return (
          <Fragment key={t.id}>
            {t.divider && (
              <span className="mx-1 my-2 w-px shrink-0 self-stretch bg-border" aria-hidden />
            )}
            <button
              role="tab"
              aria-selected={on}
              aria-disabled={t.locked || undefined}
              tabIndex={on ? 0 : -1}
              onClick={() => !t.locked && onSelect(t.id)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight") move(1);
                if (e.key === "ArrowLeft") move(-1);
              }}
              className={cn(
                "relative flex min-h-10 shrink-0 items-center gap-2 rounded-[var(--radius)] px-3.5 py-2 font-mono text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                t.locked
                  ? "cursor-not-allowed text-faint/50"
                  : on
                    ? "bg-panel-hi text-accent"
                    : "text-muted hover:bg-panel-hi/60 hover:text-fg",
              )}
            >
              {t.label}
              {t.done && !on && (
                <span className="text-[0.7rem] text-ok" aria-label="complete">
                  ✓
                </span>
              )}
              {t.meta != null && (
                <span className={cn("text-[0.65rem]", on ? "text-fg" : "text-faint")}>{t.meta}</span>
              )}
              {t.live && <span className="size-1.5 rounded-full bg-run pulse-dot" aria-hidden />}
              {on && (
                <span
                  aria-hidden
                  className="absolute inset-x-3 -bottom-px h-px bg-gradient-to-r from-transparent via-accent to-transparent"
                />
              )}
            </button>
          </Fragment>
        );
      })}
    </div>
  );
}

/** Vertical pipeline map — the workspace stages as a navigable list (not screen-switching tabs).
 *  Reuses TabItem's done/locked/live/divider semantics; the active row gets a 2px amber edge. */
export function StageRail({
  stages,
  active,
  onSelect,
}: {
  stages: TabItem[];
  active: string;
  onSelect: (id: string) => void;
}) {
  const open = stages.filter((t) => !t.locked);
  const move = (dir: 1 | -1) => {
    if (!open.length) return;
    const idx = open.findIndex((t) => t.id === active);
    const next = open[(Math.max(0, idx) + dir + open.length) % open.length];
    if (next) onSelect(next.id);
  };
  return (
    <div role="tablist" aria-orientation="vertical" aria-label="Production stages" className="flex flex-col gap-0.5">
      {stages.map((t) => {
        const on = t.id === active;
        return (
          <Fragment key={t.id}>
            {t.divider && <span className="my-1 h-px bg-border" aria-hidden />}
            <button
              role="tab"
              aria-selected={on}
              aria-disabled={t.locked || undefined}
              tabIndex={on ? 0 : -1}
              onClick={() => !t.locked && onSelect(t.id)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") move(1);
                if (e.key === "ArrowUp") move(-1);
              }}
              className={cn(
                "relative flex min-h-10 items-center gap-2 rounded-[var(--radius)] px-3 py-2 text-left font-mono text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                t.locked
                  ? "cursor-not-allowed text-faint/50"
                  : on
                    ? "bg-panel-hi text-accent"
                    : "text-muted hover:bg-panel-hi/60 hover:text-fg",
              )}
            >
              {on && (
                <span aria-hidden className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-accent" />
              )}
              <span className="min-w-0 flex-1 truncate">{t.label}</span>
              {t.done && !on && (
                <span className="text-[0.7rem] text-ok" aria-label="complete">
                  ✓
                </span>
              )}
              {t.meta != null && (
                <span className={cn("shrink-0 text-[0.65rem]", on ? "text-fg" : "text-faint")}>
                  {t.meta}
                </span>
              )}
              {t.live && <span className="size-1.5 shrink-0 rounded-full bg-run pulse-dot" aria-hidden />}
            </button>
          </Fragment>
        );
      })}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-[var(--radius)] border border-dashed border-border px-6 py-12 text-center">
      <p className="font-display text-xl text-muted">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-relaxed text-faint">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Right-hand slide-over. Escape closes; background scroll locks while open. */
export function Drawer({
  open,
  onClose,
  label,
  children,
}: {
  open: boolean;
  onClose: () => void;
  label: string;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className="drawer-in absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-border bg-bg outline-none"
      >
        {children}
      </div>
    </div>
  );
}
