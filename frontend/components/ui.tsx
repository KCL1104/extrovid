"use client";

import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type ReactNode,
} from "react";

export function cn(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

export function Button({
  variant = "default",
  loading,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "default" | "ghost" | "danger";
  loading?: boolean;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-[var(--radius)] px-3.5 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg";
  const variants = {
    primary:
      "bg-accent/15 text-accent border border-accent/40 hover:bg-accent hover:text-bg hover:border-accent",
    default: "bg-panel text-fg border border-border hover:border-border-hi hover:bg-panel-hi",
    ghost: "text-muted hover:text-fg hover:bg-panel-hi",
    danger: "text-fail border border-transparent hover:border-fail/40 hover:bg-fail/10",
  } as const;
  return (
    <button className={cn(base, variants[variant], className)} disabled={loading || props.disabled} {...props}>
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

export function Panel({
  className,
  children,
  style,
}: {
  className?: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div className={cn("rounded-[var(--radius)] border border-border bg-panel/70", className)} style={style}>
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
    verdict === "revise" || score < 6 ? "text-fail" : score < 7.5 ? "text-run" : "text-ok";
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

export function Tabs({
  tabs,
  active,
  onSelect,
}: {
  tabs: { id: string; label: string; meta?: ReactNode; live?: boolean }[];
  active: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div role="tablist" aria-label="Workspace sections" className="flex gap-1 overflow-x-auto">
      {tabs.map((t, i) => {
        const on = t.id === active;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onSelect(t.id)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") onSelect(tabs[(i + 1) % tabs.length].id);
              if (e.key === "ArrowLeft") onSelect(tabs[(i - 1 + tabs.length) % tabs.length].id);
            }}
            className={cn(
              "relative flex min-h-10 shrink-0 items-center gap-2 rounded-[var(--radius)] px-3.5 py-2 font-mono text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              on ? "bg-panel-hi text-accent" : "text-muted hover:bg-panel-hi/60 hover:text-fg",
            )}
          >
            {t.label}
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
        className="drawer-in absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-border bg-bg shadow-2xl outline-none"
      >
        {children}
      </div>
    </div>
  );
}
