"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { galleryVideoUrl, listGallery, type PublicVideo } from "@/lib/api";
import { getToken, subscribeToken } from "@/lib/auth";
import Shell from "@/components/Shell";
import { Eyebrow } from "@/components/ui";

function aspectClass(aspect: string) {
  return (
    { "9:16": "aspect-[9/16]", "16:9": "aspect-video", "1:1": "aspect-square", "4:5": "aspect-[4/5]" }[
      aspect
    ] ?? "aspect-video"
  );
}

export default function GalleryPage() {
  const [videos, setVideos] = useState<PublicVideo[] | null>(null);
  // Logged-in visitors keep the app shell (sidebar persists — no "jump out"); anonymous visitors
  // get the bare public page with a sign-in CTA. Server snapshot is null so SSR renders the bare
  // layout and the client upgrades to the shell once the token is read.
  const token = useSyncExternalStore(subscribeToken, getToken, () => null);

  useEffect(() => {
    listGallery()
      .then(setVideos)
      .catch(() => setVideos([]));
  }, []);

  const body = (
    <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-20">
      <header className="rise flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>community</Eyebrow>
          <h1 className="title mt-2 text-4xl text-fg sm:text-5xl lg:text-6xl">
            the <span className="italic text-accent">gallery</span>
          </h1>
          <p className="mt-3 max-w-lg text-sm text-muted">
            Rough cuts shared by extrovid creators — generated from a brief, assembled with AI.
          </p>
        </div>
        {!token && (
          <Link href="/" className="text-sm text-muted transition-colors hover:text-fg">
            → enter the studio
          </Link>
        )}
      </header>

      {videos === null ? (
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="aspect-video rounded-[var(--radius)] shimmer" />
          ))}
        </div>
      ) : videos.length === 0 ? (
        <p className="mt-10 text-faint">No shared videos yet — be the first to publish one.</p>
      ) : (
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {videos.map((v, i) => (
            <figure
              key={v.id}
              className="rise overflow-hidden rounded-[var(--radius)] border border-border bg-panel/70"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <video
                src={galleryVideoUrl(v.id)}
                controls
                preload="metadata"
                playsInline
                className={`${aspectClass(v.aspect_ratio)} max-h-[60vh] w-full bg-black object-contain`}
              />
              <figcaption className="flex items-center justify-between gap-2 px-4 py-3">
                <span className="min-w-0 truncate text-sm text-fg">{v.title}</span>
                <span className="shrink-0 font-mono text-[0.65rem] text-faint">{v.aspect_ratio}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </main>
  );

  return token ? <Shell>{body}</Shell> : body;
}
