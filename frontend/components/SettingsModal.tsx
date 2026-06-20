"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  changePassword,
  deleteAccount,
  getUsage,
  rotateToken,
  updatePreferences,
  type Usage,
} from "@/lib/api";
import { clearAuth, getUser, setToken, setUser } from "@/lib/auth";
import { Alert, Button, Eyebrow, Input, Pill, cn } from "@/components/ui";

// "the booth" — a two-pane director's-studio settings console. Mounted only while open
// (AccountMenu controls this), so every open starts from fresh state.

type SectionId = "account" | "usage" | "security" | "danger";

const SECTIONS: { id: SectionId; label: string; danger?: boolean }[] = [
  { id: "account", label: "account" },
  { id: "usage", label: "usage·today" },
  { id: "security", label: "security" },
  { id: "danger", label: "danger", danger: true },
];

// ── small section primitives ──

function NavRail({ active, onSelect }: { active: SectionId; onSelect: (id: SectionId) => void }) {
  const move = (dir: 1 | -1) => {
    const i = SECTIONS.findIndex((s) => s.id === active);
    onSelect(SECTIONS[(i + dir + SECTIONS.length) % SECTIONS.length].id);
  };
  return (
    <div
      role="tablist"
      aria-orientation="vertical"
      aria-label="Settings sections"
      className="flex shrink-0 flex-col gap-0.5 border-b border-border p-3 max-sm:flex-row max-sm:overflow-x-auto sm:w-44 sm:border-b-0 sm:border-r"
    >
      {SECTIONS.map((s) => {
        const on = s.id === active;
        return (
          <button
            key={s.id}
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onSelect(s.id)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || e.key === "ArrowRight") {
                e.preventDefault();
                move(1);
              }
              if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
                e.preventDefault();
                move(-1);
              }
            }}
            className={cn(
              "relative flex min-h-10 shrink-0 items-center rounded-[var(--radius)] px-3 py-2 text-left font-mono text-xs transition-colors",
              s.danger
                ? on
                  ? "bg-fail/10 text-fail"
                  : "text-fail/70 hover:text-fail"
                : on
                  ? "bg-panel-hi text-accent"
                  : "text-muted hover:bg-panel-hi/60 hover:text-fg",
            )}
          >
            {on && (
              <span
                aria-hidden
                className={cn(
                  // left sideline on desktop; bottom underline when the rail goes horizontal
                  "absolute inset-y-1.5 left-0 w-0.5 rounded-full max-sm:inset-x-2 max-sm:inset-y-auto max-sm:bottom-0 max-sm:h-0.5 max-sm:w-auto",
                  s.danger ? "bg-fail" : "bg-accent",
                )}
              />
            )}
            {s.label}
          </button>
        );
      })}
    </div>
  );
}

function SectionHead({ eyebrow, line, danger }: { eyebrow: string; line: string; danger?: boolean }) {
  return (
    <div className="mb-4">
      <Eyebrow className={danger ? "text-fail" : undefined}>{eyebrow}</Eyebrow>
      <p className={cn("mt-1 font-display text-lg lowercase", danger ? "text-fail/80" : "text-muted")}>
        {line}
      </p>
    </div>
  );
}

function SettingRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <span className="shrink-0 font-mono text-xs text-faint">{label}</span>
      <span className="min-w-0 truncate text-right font-mono text-xs text-fg tabular-nums">
        {children}
      </span>
    </div>
  );
}

// amber level-gauge; calm by default, flips to fail + a live pulse dot at cap
function Meter({ label, n, cap }: { label: string; n: number; cap: number }) {
  const unlimited = cap === 0;
  const atCap = cap > 0 && n >= cap;
  const pct = cap > 0 ? Math.min(100, Math.round((n / cap) * 100)) : 0;
  return (
    <div>
      <div className="flex items-center justify-between font-mono text-xs">
        <span className="text-faint">{label}</span>
        {unlimited ? (
          <span className="text-muted">∞</span>
        ) : (
          <span className={cn("inline-flex items-center gap-1.5 tabular-nums", atCap && "text-fail")}>
            {atCap && <span className="size-1.5 rounded-full bg-current pulse-dot" aria-hidden />}
            <span className={atCap ? undefined : "text-fg"}>{n}</span>
            <span className={atCap ? undefined : "text-faint"}>/{cap}</span>
          </span>
        )}
      </div>
      {!unlimited && (
        <div
          className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-bg-soft"
          role="progressbar"
          aria-label={`${label} usage`}
          aria-valuenow={n}
          aria-valuemin={0}
          aria-valuemax={cap}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300 ease-out",
              atCap ? "bg-fail" : "bg-accent",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function memberSince(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

// ── modal ──

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const user = getUser();
  const hasPassword = user?.has_password !== false; // default true for older cached records
  const panelRef = useRef<HTMLDivElement>(null);

  const [active, setActive] = useState<SectionId>("account");
  const [usage, setUsage] = useState<Usage | null>(null);
  // advisory default format for new projects (pre-fills the per-project length selector)
  const [defFmt, setDefFmt] = useState<string>(user?.default_format ?? "");
  const [fmtBusy, setFmtBusy] = useState(false);
  async function saveDefaultFormat(v: string) {
    setDefFmt(v);
    setFmtBusy(true);
    try {
      const updated = await updatePreferences(v || null);
      setUser(updated);
      // mirror to the per-project picker's remembered default so it takes effect immediately
      if (typeof window !== "undefined" && v) localStorage.setItem("extrovid:format", v);
    } catch {
      /* advisory pref — ignore transient failures */
    } finally {
      setFmtBusy(false);
    }
  }

  // password change
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [currentPw, setCurrentPw] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwOk, setPwOk] = useState(false);

  // reset access (rotate token)
  const [resetBusy, setResetBusy] = useState(false);
  const [resetOk, setResetOk] = useState(false);

  // delete account
  const [armed, setArmed] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [delBusy, setDelBusy] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);

  // Load today's usage; lock background scroll, close on Escape, focus the active tab.
  useEffect(() => {
    getUsage()
      .then(setUsage)
      .catch(() => {});
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panelRef.current?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus();
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  async function submitPassword() {
    if (pwBusy) return;
    setPwError(null);
    setPwOk(false);
    if (newPw.length < 8) return setPwError("New password must be at least 8 characters.");
    if (newPw !== confirmPw) return setPwError("Passwords don't match.");
    setPwBusy(true);
    try {
      await changePassword(newPw, hasPassword ? currentPw : undefined);
      setPwOk(true);
      setNewPw("");
      setConfirmPw("");
      setCurrentPw("");
    } catch (e) {
      setPwError(e instanceof Error ? e.message : "Could not update password.");
    } finally {
      setPwBusy(false);
    }
  }

  async function resetAccess() {
    if (resetBusy) return;
    setResetBusy(true);
    try {
      const { token } = await rotateToken();
      setToken(token); // keep THIS device signed in; others are now invalid
      setResetOk(true);
    } catch {
      /* leave the prior token in place on failure */
    } finally {
      setResetBusy(false);
    }
  }

  async function confirmDelete() {
    if (delBusy) return;
    setDelBusy(true);
    setDelError(null);
    try {
      await deleteAccount();
      clearAuth();
      window.location.assign("/");
    } catch (e) {
      setDelError(e instanceof Error ? e.message : "Could not delete account — please try again.");
      setDelBusy(false);
    }
  }

  function signOut() {
    clearAuth();
    window.location.assign("/");
  }

  const since = memberSince(user?.created_at);
  const deleteReady = confirmEmail.trim().toLowerCase() === (user?.email ?? "").toLowerCase();

  // Portal to <body>: the sidebar's lg:translate-x-0 transform would otherwise become the
  // containing block for this fixed overlay, trapping it inside the 256px rail.
  const modal = (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm max-sm:items-start"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
        className="rise relative my-auto flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-[var(--radius)] border border-border bg-panel shadow-2xl max-sm:my-4"
      >
        {/* header */}
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <Eyebrow>settings</Eyebrow>
            <h2 id="settings-title" className="title font-display text-2xl lowercase text-fg">
              the booth
            </h2>
            <p className="truncate font-mono text-xs text-faint">{user?.email ?? "account"}</p>
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="Close settings" className="-mr-1 shrink-0 px-2">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </Button>
        </header>

        {/* body: nav rail + content pane */}
        <div className="flex min-h-0 flex-1 max-sm:flex-col">
          <NavRail active={active} onSelect={setActive} />

          <div
            role="tabpanel"
            aria-label={active}
            tabIndex={0}
            className="min-w-0 flex-1 overflow-y-auto px-6 py-5 outline-none"
          >
            <div className="max-w-[34rem]">
              {/* ── account ── */}
              {active === "account" && (
                <>
                  <SectionHead eyebrow="account" line="your seat in the studio." />
                  <div className="divide-y divide-border overflow-hidden rounded-[var(--radius)] border border-border bg-panel/70">
                    <SettingRow label="email">{user?.email ?? "—"}</SettingRow>
                    <SettingRow label="plan">
                      {user?.is_admin ? (
                        <Pill className="border-accent/40 bg-accent/10 text-accent">admin · unlimited</Pill>
                      ) : (
                        <Pill>free</Pill>
                      )}
                    </SettingRow>
                    <SettingRow label="sign-in">
                      <Pill>{user?.is_google ? "google" : hasPassword ? "password" : "—"}</Pill>
                    </SettingRow>
                    {since && <SettingRow label="member since">{since}</SettingRow>}
                    {!user?.is_admin && (
                      <SettingRow label="default format">
                        <select
                          value={defFmt}
                          onChange={(e) => saveDefaultFormat(e.target.value)}
                          disabled={fmtBusy}
                          aria-label="Default format for new projects"
                          className="rounded-[var(--radius)] border border-border bg-bg-soft px-2 py-1 font-mono text-xs text-fg outline-none focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
                        >
                          <option value="">Ask each time</option>
                          <option value="social">Social clip</option>
                          <option value="ad">Ad / Promo</option>
                          <option value="explainer">Explainer</option>
                          <option value="youtube">YouTube</option>
                          <option value="documentary">Documentary</option>
                        </select>
                      </SettingRow>
                    )}
                  </div>
                  {!user?.is_admin && (
                    <p className="mt-2 px-1 text-xs leading-relaxed text-faint">
                      Pre-fills the length/format on new projects — you can still change it per
                      video at the Plan step.
                    </p>
                  )}
                </>
              )}

              {/* ── usage · today ── */}
              {active === "usage" && (
                <>
                  <SectionHead eyebrow="usage · today" line="today's burn." />
                  <div className="rounded-[var(--radius)] border border-border bg-panel/70 p-4">
                    {usage ? (
                      <div className="space-y-3.5">
                        <Meter label="videos" n={usage.videos_today} cap={usage.video_cap} />
                        <Meter label="images" n={usage.images_today} cap={usage.image_cap} />
                        <Meter label="voiceovers" n={usage.audio_today} cap={usage.audio_cap} />
                        <div className="border-t border-border pt-3">
                          <Eyebrow>est. spend · today</Eyebrow>
                          <p className="mt-1 font-mono text-xl text-accent tabular-nums">
                            ${usage.est_spend_usd.toFixed(2)}
                          </p>
                        </div>
                        {usage.failed_today > 0 && (
                          <span className="inline-flex items-center gap-1.5 font-mono text-xs text-fail">
                            <span className="size-1.5 rounded-full bg-current pulse-dot" aria-hidden />
                            {usage.failed_today} failed today
                          </span>
                        )}
                      </div>
                    ) : (
                      // skeleton matching real row height — no layout shift on load
                      <div className="space-y-3.5" aria-hidden>
                        {[0, 1, 2].map((i) => (
                          <div key={i}>
                            <div className="h-3 w-16 rounded-full shimmer" />
                            <div className="mt-1.5 h-1.5 w-full rounded-full shimmer" />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* ── security ── */}
              {active === "security" && (
                <>
                  <SectionHead eyebrow="security" line="keys to the booth." />
                  <div className="divide-y divide-border overflow-hidden rounded-[var(--radius)] border border-border bg-panel/70">
                    {/* password */}
                    <div className="p-4">
                      <p className="text-xs leading-relaxed text-faint">
                        {hasPassword
                          ? "Change your password."
                          : "Set a password so you can sign in without Google."}
                      </p>
                      <div className="mt-3 flex flex-col gap-2">
                        {hasPassword && (
                          <Input
                            type="password"
                            autoComplete="current-password"
                            value={currentPw}
                            onChange={(e) => setCurrentPw(e.target.value)}
                            placeholder="Current password"
                          />
                        )}
                        <Input
                          type="password"
                          autoComplete="new-password"
                          value={newPw}
                          onChange={(e) => setNewPw(e.target.value)}
                          placeholder="New password (min 8 chars)"
                        />
                        <Input
                          type="password"
                          autoComplete="new-password"
                          value={confirmPw}
                          onChange={(e) => setConfirmPw(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && submitPassword()}
                          placeholder="Confirm new password"
                        />
                        {pwError && <Alert>{pwError}</Alert>}
                        {pwOk && (
                          <span className="inline-flex items-center gap-1.5 font-mono text-xs text-ok">
                            <span className="size-1.5 rounded-full bg-current" aria-hidden />
                            Password updated.
                          </span>
                        )}
                        <div>
                          <Button
                            variant="primary"
                            onClick={submitPassword}
                            loading={pwBusy}
                            disabled={!newPw || !confirmPw || (hasPassword && !currentPw)}
                          >
                            {hasPassword ? "Update password" : "Set password"}
                          </Button>
                        </div>
                      </div>
                    </div>

                    {/* reset access */}
                    <div className="p-4">
                      <p className="text-sm text-fg">Reset access</p>
                      <p className="mt-1 text-xs leading-relaxed text-faint">
                        Signs out every other device. This one stays signed in.
                      </p>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Button variant="default" onClick={resetAccess} loading={resetBusy}>
                          Reset access
                        </Button>
                        <Button variant="ghost" onClick={signOut}>
                          Sign out
                        </Button>
                        {resetOk && (
                          <span className="inline-flex items-center gap-1.5 font-mono text-xs text-ok">
                            <span className="size-1.5 rounded-full bg-current" aria-hidden />
                            Other devices signed out.
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* ── danger zone ── */}
              {active === "danger" && (
                <>
                  <SectionHead eyebrow="danger zone" line="the point of no return." danger />
                  <div className="rounded-[var(--radius)] border border-fail/30 bg-bg-soft p-4">
                    <p className="text-xs leading-relaxed text-muted">
                      This permanently deletes your account and every project — scenes, shots,
                      generated images and videos, and any cut. This can’t be undone.
                    </p>
                    {!armed ? (
                      <div className="mt-3">
                        <Button variant="danger" onClick={() => setArmed(true)}>
                          Delete account
                        </Button>
                      </div>
                    ) : (
                      <>
                        <label className="mt-3 block">
                          <span className="text-xs text-faint">
                            Type <span className="font-mono text-fg">{user?.email}</span> to confirm
                          </span>
                          <Input
                            autoFocus
                            className="mt-1"
                            value={confirmEmail}
                            onChange={(e) => setConfirmEmail(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && deleteReady) confirmDelete();
                            }}
                            placeholder={user?.email}
                          />
                        </label>
                        {delError && (
                          <div className="mt-2">
                            <Alert>{delError}</Alert>
                          </div>
                        )}
                        <div className="mt-3 flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setArmed(false);
                              setConfirmEmail("");
                            }}
                          >
                            Cancel
                          </Button>
                          <Button
                            variant="danger"
                            loading={delBusy}
                            disabled={!deleteReady}
                            onClick={confirmDelete}
                          >
                            Delete account
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return typeof document === "undefined" ? null : createPortal(modal, document.body);
}
