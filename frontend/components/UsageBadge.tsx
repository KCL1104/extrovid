"use client";

import { useCallback, useEffect, useState } from "react";
import { getUsage, type Usage } from "@/lib/api";

export default function UsageBadge() {
  const [u, setU] = useState<Usage | null>(null);

  const load = useCallback(async () => {
    try {
      setU(await getUsage());
    } catch {
      /* ignore — badge is best-effort */
    }
  }, []);

  useEffect(() => {
    load();
    const onChange = () => load();
    window.addEventListener("extrovid-usage-changed", onChange);
    return () => window.removeEventListener("extrovid-usage-changed", onChange);
  }, [load]);

  if (!u) return null;
  const near = (n: number, cap: number) => cap > 0 && n >= cap;
  const cls = (n: number, cap: number) => (near(n, cap) ? "text-fail" : "text-muted");

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full border border-border-hi bg-bg-soft px-3 py-1 font-mono text-[0.7rem]"
      title="Today's paid generations · estimated spend"
    >
      <span className="text-faint">today</span>
      <span className={cls(u.videos_today, u.video_cap)}>
        🎬 {u.videos_today}{u.video_cap > 0 ? `/${u.video_cap}` : ""}
      </span>
      <span className={cls(u.images_today, u.image_cap)}>
        🖼 {u.images_today}{u.image_cap > 0 ? `/${u.image_cap}` : ""}
      </span>
      <span className="text-accent">~${u.est_spend_usd.toFixed(2)}</span>
      {u.failed_today > 0 && <span className="text-fail" title="failed jobs today">⚠ {u.failed_today}</span>}
    </div>
  );
}
