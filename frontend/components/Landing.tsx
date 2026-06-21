"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { galleryVideoUrl, listGallery, type PublicVideo } from "@/lib/api";
import { Button, Eyebrow } from "@/components/ui";

// The public face of the product — the pipeline IS the pitch (the spec's "script-first,
// not timeline-first"). Shown to logged-out visitors at the root; the CTA reveals sign-in.
const STAGES = ["brief", "script", "look", "cast", "storyboard", "rough cut"];

export default function Landing({ onEnter }: { onEnter: () => void }) {
  const [videos, setVideos] = useState<PublicVideo[] | null>(null);

  useEffect(() => {
    listGallery()
      .then((v) => setVideos(v.slice(0, 3)))
      .catch(() => setVideos([]));
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16">
      {/* hero — the wordmark as a "now showing" title card */}
      <div className="rise">
        <Eyebrow>now showing · an AI-native director</Eyebrow>
        <h1 className="title mt-4 text-6xl lowercase text-fg sm:text-7xl lg:text-8xl">
          extro<span className="italic text-accent">vid</span>
        </h1>
        <div className="mt-4 h-px w-full max-w-md bg-gradient-to-r from-accent/60 via-border to-transparent" />
        <p className="title mt-6 text-3xl text-muted sm:text-4xl">
          direct a film from a <span className="italic text-accent">brief</span>.
        </p>
        <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
          Not a timeline you fill with footage — a studio that writes the script,
          previsualizes the look, generates each shot with consistent characters, and
          assembles the cut. You direct; the models execute.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Button variant="primary" onClick={onEnter} className="px-5 py-2.5 text-base">
            Enter the studio →
          </Button>
          <Link href="/gallery" className="text-sm text-muted transition-colors hover:text-fg">
            view the gallery
          </Link>
        </div>
      </div>

      {/* the pipeline, as the pitch */}
      <div className="rise mt-14" style={{ animationDelay: "80ms" }}>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
          {STAGES.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <span className="rounded-full border border-border-hi bg-bg-soft px-3 py-1 font-mono text-[0.7rem] uppercase tracking-wider text-muted">
                {s}
              </span>
              {i < STAGES.length - 1 && (
                <span className="text-faint" aria-hidden>
                  →
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="mt-4 h-px w-full bg-gradient-to-r from-accent/50 via-border to-transparent" />
      </div>

      {/* gallery teaser (public; quietly omitted when empty) */}
      {videos && videos.length > 0 && (
        <div className="rise mt-12" style={{ animationDelay: "160ms" }}>
          <Eyebrow>from the gallery</Eyebrow>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            {videos.map((v) => (
              <figure
                key={v.id}
                className="overflow-hidden rounded-[var(--radius)] border border-border bg-panel/70"
              >
                <video
                  src={galleryVideoUrl(v.id)}
                  preload="metadata"
                  playsInline
                  muted
                  className="aspect-video w-full bg-black object-cover"
                />
                <figcaption className="truncate px-3 py-2 text-xs text-muted">{v.title}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
