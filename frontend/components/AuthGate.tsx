"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { clearAuth, getToken, setUser } from "@/lib/auth";
import { me } from "@/lib/api";
import AuthScreen from "@/components/AuthScreen";

// Routes that render without a session (the public gallery + the OAuth landing).
const PUBLIC_PREFIXES = ["/gallery", "/auth/callback"];

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [token, setTok] = useState<string | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    setMounted(true);
    setTok(getToken());
    // Mid-session 401 (revoked/expired token): api() clears auth + fires this → back to the gate.
    const onUnauth = () => setTok(null);
    window.addEventListener("extrovid-unauthorized", onUnauth);
    return () => window.removeEventListener("extrovid-unauthorized", onUnauth);
  }, []);

  // With a token, refresh the cached user (and validate the token — a 401 here bounces us out).
  useEffect(() => {
    if (token) me().then(setUser).catch(() => {});
  }, [token]);

  if (!mounted) return null; // avoid hydration mismatch (localStorage is client-only)

  if (PUBLIC_PREFIXES.some((p) => pathname?.startsWith(p))) return <>{children}</>;
  if (!token) return <AuthScreen onAuthed={(t) => setTok(t)} />;
  return <>{children}</>;
}
