"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setToken } from "@/lib/auth";
import { Eyebrow } from "@/components/ui";

// Google OAuth lands here as /auth/callback?token=... (or ?error=...). We stash the token and
// bounce to the dashboard. useSearchParams must live under a Suspense boundary in Next 16.
function CallbackInner() {
  const params = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const token = params.get("token");
    if (token) {
      setToken(token);
      router.replace("/");
    } else {
      router.replace("/?auth_error=google");
    }
  }, [params, router]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="rise">
        <Eyebrow>extrovid · access</Eyebrow>
        <p className="mt-3 text-sm text-muted">Signing you in…</p>
      </div>
    </main>
  );
}

export default function AuthCallback() {
  return (
    <Suspense fallback={null}>
      <CallbackInner />
    </Suspense>
  );
}
