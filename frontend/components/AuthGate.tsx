"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { getToken, setUser } from "@/lib/auth";
import { me } from "@/lib/api";
import AuthScreen from "@/components/AuthScreen";
import Landing from "@/components/Landing";

// Routes that render without a session (the public gallery + the OAuth landing).
const PUBLIC_PREFIXES = ["/gallery", "/auth/callback"];

// Token as an external store: localStorage value, invalidated by the 401 broadcast.
// Server snapshot is null so SSR + first client render agree (no hydration gate needed).
function subscribeToken(onChange: () => void) {
  window.addEventListener("extrovid-unauthorized", onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener("extrovid-unauthorized", onChange);
    window.removeEventListener("storage", onChange);
  };
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const storedToken = useSyncExternalStore(subscribeToken, getToken, () => null);
  // freshly-issued token from the sign-in screen (covers the gap before storage settles)
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  // logged-out root shows the public landing first; the CTA reveals the sign-in screen
  const [showAuth, setShowAuth] = useState(false);
  const pathname = usePathname();
  const token = storedToken ?? sessionToken;

  // Mid-session 401 also invalidates a token minted on this screen this session.
  useEffect(() => {
    const onUnauth = () => setSessionToken(null);
    window.addEventListener("extrovid-unauthorized", onUnauth);
    return () => window.removeEventListener("extrovid-unauthorized", onUnauth);
  }, []);

  // With a token, refresh the cached user (and validate the token — a 401 here bounces us out).
  useEffect(() => {
    if (token) me().then(setUser).catch(() => {});
  }, [token]);

  if (PUBLIC_PREFIXES.some((p) => pathname?.startsWith(p))) return <>{children}</>;
  if (!token) {
    // landing only at the root; a deep link to a gated route goes straight to sign-in
    if (pathname === "/" && !showAuth) return <Landing onEnter={() => setShowAuth(true)} />;
    return <AuthScreen onAuthed={(t) => setSessionToken(t)} />;
  }
  return <>{children}</>;
}
