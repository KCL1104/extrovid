"use client";

import { useState } from "react";
import { googleLoginUrl, login, register } from "@/lib/api";
import { setAuth } from "@/lib/auth";
import { Alert, Button, Eyebrow, Panel } from "@/components/ui";

const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";
const field =
  "mt-1 w-full rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 text-sm text-fg outline-none placeholder:text-faint focus:border-accent/60";

export default function AuthScreen({ onAuthed }: { onAuthed: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (busy) return;
    const e = email.trim();
    if (!e || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = mode === "login" ? await login(e, password) : await register(e, password);
      setAuth(res.token, res.user);
      onAuthed(res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function tab(m: "login" | "register", label: string) {
    const active = mode === m;
    return (
      <button
        type="button"
        onClick={() => {
          setMode(m);
          setError(null);
        }}
        className={`border-b-2 pb-2 text-sm transition-colors ${
          active ? "border-accent text-fg" : "border-transparent text-faint hover:text-muted"
        }`}
      >
        {label}
      </button>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="rise">
        <Eyebrow>extrovid · access</Eyebrow>
        <h1 className="title mt-3 text-5xl text-fg">
          {mode === "login" ? (
            <>
              welcome <span className="italic text-accent">back</span>
            </>
          ) : (
            <>
              create your <span className="italic text-accent">account</span>
            </>
          )}
        </h1>
        <p className="mt-4 text-sm text-muted">
          Brief to rough cut — sign in to plan, generate, and assemble.
        </p>

        <Panel className="mt-6 p-5">
          <div className="flex items-center gap-5">
            {tab("login", "Sign in")}
            {tab("register", "Register")}
          </div>

          <div className="mt-4 flex flex-col gap-3">
            <label>
              <span className="text-xs text-faint">Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                disabled={busy}
                autoFocus
                placeholder="you@studio.com"
                className={`${field} ${focusRing}`}
              />
            </label>
            <label>
              <span className="text-xs text-faint">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                disabled={busy}
                placeholder={mode === "register" ? "at least 8 characters" : "your password"}
                className={`${field} ${focusRing}`}
              />
            </label>
            <Button variant="primary" onClick={submit} loading={busy} className="mt-1 w-full">
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </div>

          <div className="my-4 flex items-center gap-3 text-faint">
            <div className="h-px flex-1 bg-border" />
            <span className="font-mono text-[0.6rem] uppercase tracking-wider">or</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <a
            href={googleLoginUrl()}
            className={`flex w-full items-center justify-center gap-2 rounded-[var(--radius)] border border-border bg-panel px-3.5 py-2 text-sm font-medium text-fg transition-colors hover:border-border-hi hover:bg-panel-hi ${focusRing}`}
          >
            <GoogleMark />
            Continue with Google
          </a>
        </Panel>

        {error && (
          <div className="mt-3">
            <Alert>{error}</Alert>
          </div>
        )}
      </div>
    </main>
  );
}

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.6 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.6 6.1 29.6 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.6 6.1 29.6 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 10-2 13.6-5.2l-6.3-5.3C29.2 35 26.7 36 24 36c-5.3 0-9.7-3.4-11.3-8.1l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4 5.5l6.3 5.3C41.9 34.8 44 29.8 44 24c0-1.3-.1-2.3-.4-3.5z"
      />
    </svg>
  );
}
