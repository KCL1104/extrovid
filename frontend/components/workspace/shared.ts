// Shared helpers for the project workspace panels.

import type { Shot, ShotVersion } from "@/lib/api";

// mock:// URLs (and anything non-http) are not playable/renderable.
export const isPlayable = (u?: string | null): u is string => !!u && /^https?:/i.test(u);

export const isRunning = (v: ShotVersion) =>
  v.job_status === "running" || v.job_status === "queued";

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function aspectClass(aspect: string) {
  return (
    { "9:16": "aspect-[9/16]", "16:9": "aspect-video", "1:1": "aspect-square", "4:5": "aspect-[4/5]" }[
      aspect
    ] ?? "aspect-video"
  );
}

/** The take that represents a shot in the cut: selected, else the latest finished one. */
export function chosenTake(versions: ShotVersion[]): ShotVersion | undefined {
  const finished = versions.filter((v) => v.output_asset_id);
  return finished.find((v) => v.selected) ?? finished[finished.length - 1];
}

/** A shot is "rendered" once any take has an output asset (true in mock AND real mode). */
export const isRendered = (versions: ShotVersion[]) => versions.some((v) => v.output_asset_id);

export function fmtDuration(sec?: number | null) {
  return sec == null ? "—" : `${sec.toFixed(1)}s`;
}

export function relTime(iso?: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime();
  const d = Math.max(0, Date.now() - t);
  const m = Math.floor(d / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export const cameraLine = (shot: Shot) =>
  `${shot.camera_spec.shot_size} · ${shot.camera_spec.angle} · ${shot.camera_spec.movement}` +
  (shot.camera_spec.lens ? ` · ${shot.camera_spec.lens}` : "");

export const usageChanged = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("extrovid-usage-changed"));
};
