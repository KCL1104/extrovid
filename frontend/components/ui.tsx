"use client";

import { type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from "react";

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
