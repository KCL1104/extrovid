"use client";

import { useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/auth";
import { getUsage } from "@/lib/api";
import { Alert, Button, Eyebrow, Panel } from "@/components/ui";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [token, setTok] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    setMounted(true);
    setTok(getToken());
    // Mid-session 401 (e.g. token revoked): bounce back to the gate with an explanation.
    // During an in-flight submit() this runs first; the catch below then overrides with the
    // submit-time message (event dispatch is synchronous, the await-catch resolves after).
    const onUnauth = () => {
      setTok(null);
      setError("Your session ended — please re-enter your access token.");
    };
    window.addEventListener("extrovid-unauthorized", onUnauth);
    return () => window.removeEventListener("extrovid-unauthorized", onUnauth);
  }, []);

  async function submit() {
    const t = input.trim();
    if (!t || checking) return;
    setError(null);
    setChecking(true);
    setToken(t); // write first so api() reads it from localStorage on the probe
    try {
      await getUsage(); // cheap auth probe — GET /api/usage is token-gated
      setTok(t); // success → gate unmounts, app renders (only here, never eagerly)
      setInput("");
    } catch (e) {
      // 401: api() already cleared the token. Network error: token kept for retry.
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        /unauthor/i.test(msg)
          ? "That token was rejected — check it and try again."
          : "Couldn't reach the server — check your connection and try again.",
      );
    } finally {
      setChecking(false);
    }
  }

  if (!mounted) return null; // avoid hydration mismatch (localStorage is client-only)

  if (!token) {
    const contact = process.env.NEXT_PUBLIC_OWNER_CONTACT;
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
        <div className="rise">
          <Eyebrow>extrovid · access</Eyebrow>
          <h1 className="title mt-3 text-5xl text-fg">
            enter your <span className="italic text-accent">token</span>
          </h1>
          <p className="mt-3 text-sm text-muted">This deployment is private. Paste the access token to continue.</p>
          <Panel className="mt-6 p-4">
            <div className="flex gap-2">
              <input
                type="password"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  if (error) setError(null);
                }}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                disabled={checking}
                autoFocus
                placeholder="access token"
                className="min-w-0 flex-1 rounded-[var(--radius)] border border-border bg-bg-soft px-3 py-2 font-mono text-sm text-fg outline-none placeholder:text-faint focus:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
              />
              <Button variant="primary" onClick={submit} loading={checking}>Enter</Button>
            </div>
          </Panel>
          {error && (
            <div className="mt-3">
              <Alert>{error}</Alert>
            </div>
          )}
          <p className="mt-3 text-xs text-faint">
            {contact ? (
              <>
                Need access?{" "}
                <a href={`mailto:${contact}`} className="text-accent hover:underline">
                  Contact {contact}
                </a>
              </>
            ) : (
              "Don't have a token? Ask the deployment owner for access."
            )}
          </p>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
