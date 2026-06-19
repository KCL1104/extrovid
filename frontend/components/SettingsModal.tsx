"use client";

import { useEffect, useState } from "react";
import {
  changePassword,
  deleteAccount,
  getUsage,
  rotateToken,
  type Usage,
} from "@/lib/api";
import { clearAuth, getUser, setToken } from "@/lib/auth";
import { Alert, Button, Eyebrow, cn } from "@/components/ui";

const field =
  "mt-1 w-full rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-sm text-fg outline-none placeholder:text-faint focus:border-accent/60";
const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-border px-5 py-4 first:border-t-0">
      <Eyebrow>{title}</Eyebrow>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-sm">
      <span className="text-faint">{label}</span>
      <span className="min-w-0 truncate text-fg">{children}</span>
    </div>
  );
}

function UsageRow({ label, n, cap }: { label: string; n: number; cap: number }) {
  const atCap = cap > 0 && n >= cap;
  const pct = cap > 0 ? Math.min(100, Math.round((n / cap) * 100)) : 0;
  return (
    <div className="mt-2.5 first:mt-0">
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

function memberSince(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

// Mounted only while open (see AccountMenu) — so every open starts from fresh state.
export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const user = getUser();
  const [usage, setUsage] = useState<Usage | null>(null);

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

  const hasPassword = user?.has_password !== false; // default true for older cached records

  // Load today's usage; lock background scroll and close on Escape while mounted.
  useEffect(() => {
    getUsage()
      .then(setUsage)
      .catch(() => {});
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
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

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="my-auto w-full max-w-md rounded-[var(--radius)] border border-border bg-panel shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="title text-2xl text-fg">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="-mr-2 inline-flex size-9 items-center justify-center rounded-[var(--radius)] text-faint transition-colors hover:bg-panel-hi hover:text-fg"
          >
            ✕
          </button>
        </div>

        <Section title="Account">
          <Row label="Email">{user?.email ?? "—"}</Row>
          <Row label="Plan">{user?.is_admin ? "Admin · unlimited" : "Free"}</Row>
          <Row label="Sign-in">{user?.is_google ? "Google" : hasPassword ? "Password" : "—"}</Row>
          {since && <Row label="Member since">{since}</Row>}
        </Section>

        <Section title="Usage · today">
          {usage ? (
            <>
              <UsageRow label="Videos" n={usage.videos_today} cap={usage.video_cap} />
              <UsageRow label="Images" n={usage.images_today} cap={usage.image_cap} />
              <UsageRow label="Voiceovers" n={usage.audio_today} cap={usage.audio_cap} />
              <div className="mt-3 flex items-center justify-between border-t border-border pt-2 font-mono text-[0.7rem]">
                <span className="text-faint">est. spend</span>
                <span className="text-accent">~${usage.est_spend_usd.toFixed(2)}</span>
              </div>
              {usage.failed_today > 0 && (
                <p className="mt-1 font-mono text-[0.7rem] text-fail">
                  ⚠ {usage.failed_today} failed today
                </p>
              )}
            </>
          ) : (
            <p className="font-mono text-[0.7rem] text-faint">loading…</p>
          )}
        </Section>

        <Section title="Security">
          <p className="text-xs leading-relaxed text-faint">
            {hasPassword
              ? "Change your password."
              : "Set a password so you can sign in without Google."}
          </p>
          <div className="mt-3 flex flex-col gap-2">
            {hasPassword && (
              <input
                type="password"
                autoComplete="current-password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                placeholder="Current password"
                className={`${field} ${focusRing}`}
              />
            )}
            <input
              type="password"
              autoComplete="new-password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              placeholder="New password (min 8 chars)"
              className={`${field} ${focusRing}`}
            />
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitPassword()}
              placeholder="Confirm new password"
              className={`${field} ${focusRing}`}
            />
            {pwError && <Alert>{pwError}</Alert>}
            {pwOk && <p className="font-mono text-[0.7rem] text-ok">✓ Password updated.</p>}
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

          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
            <Button variant="default" onClick={resetAccess} loading={resetBusy}>
              Reset access
            </Button>
            <Button variant="ghost" onClick={signOut}>
              Sign out
            </Button>
            {resetOk ? (
              <span className="font-mono text-[0.7rem] text-ok">✓ Other devices signed out.</span>
            ) : (
              <span className="text-[0.7rem] text-faint">Signs out all other devices.</span>
            )}
          </div>
        </Section>

        <Section title="Danger zone">
          {!armed ? (
            <Button variant="danger" onClick={() => setArmed(true)}>
              Delete account
            </Button>
          ) : (
            <div className="rounded-[var(--radius)] border border-fail/30 p-3">
              <p className="text-xs leading-relaxed text-muted">
                This permanently deletes your account and every project — scenes, shots, generated
                images and videos, and any cut. This can’t be undone.
              </p>
              <label className="mt-3 block">
                <span className="text-xs text-faint">
                  Type <span className="font-mono text-fg">{user?.email}</span> to confirm
                </span>
                <input
                  autoFocus
                  value={confirmEmail}
                  onChange={(e) => setConfirmEmail(e.target.value)}
                  placeholder={user?.email}
                  className={`${field} ${focusRing}`}
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
                  disabled={confirmEmail.trim().toLowerCase() !== (user?.email ?? "").toLowerCase()}
                  onClick={confirmDelete}
                >
                  Delete account
                </Button>
              </div>
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
