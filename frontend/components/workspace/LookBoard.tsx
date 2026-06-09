"use client";

import { useState } from "react";
import { CornerDownRight, Sparkles } from "lucide-react";
import type { ConceptSet, LookFrame } from "@/lib/api";
import { Button, EmptyState, Eyebrow, Panel, StatusBadge, cn } from "@/components/ui";
import { aspectClass, isPlayable } from "@/components/workspace/shared";

export default function LookBoard({
  conceptSets,
  aspect,
  busy,
  onGenerate,
  onPromote,
  onRefine,
}: {
  conceptSets: ConceptSet[];
  aspect: string;
  busy: Record<string, boolean>;
  onGenerate: (csId: string) => void;
  onPromote: (frameId: string, target: string) => void;
  onRefine: (frameId: string, instruction: string) => Promise<void>;
}) {
  if (conceptSets.length === 0) {
    return (
      <EmptyState
        title="No looks yet"
        hint="Plan the production first — the AI art director proposes concept sets per scene, which you generate, refine, and promote into production memory."
      />
    );
  }
  return (
    <div className="space-y-5">
      <p className="text-xs leading-relaxed text-faint">
        Generate concepts, then iterate: <span className="text-fg">refine</span> a frame with
        Qwen-Image-Edit instead of rerolling, promote the keeper as{" "}
        <span className="text-fg">first frame</span> (feeds i2v) or{" "}
        <span className="text-fg">cast</span> (reusable character for r2v consistency).
      </p>
      {conceptSets.map((cs, i) => (
        <ConceptSetCard
          key={cs.id}
          cs={cs}
          aspect={aspect}
          busy={!!busy[cs.id]}
          onGenerate={() => onGenerate(cs.id)}
          onPromote={onPromote}
          onRefine={onRefine}
          delay={i * 40}
        />
      ))}
    </div>
  );
}

function ConceptSetCard({
  cs,
  aspect,
  busy,
  onGenerate,
  onPromote,
  onRefine,
  delay,
}: {
  cs: ConceptSet;
  aspect: string;
  busy: boolean;
  onGenerate: () => void;
  onPromote: (frameId: string, target: string) => void;
  onRefine: (frameId: string, instruction: string) => Promise<void>;
  delay: number;
}) {
  const [refineId, setRefineId] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [refining, setRefining] = useState(false);

  const hasImages = cs.look_frames.some((f) => isPlayable(f.image_url));
  const triedButNoPreview = !hasImages && cs.status === "generated";
  const refineTarget = cs.look_frames.find((f) => f.id === refineId);

  async function applyRefine() {
    if (!refineId || !instruction.trim() || refining) return;
    setRefining(true);
    try {
      await onRefine(refineId, instruction.trim());
      setInstruction("");
      setRefineId(null);
    } finally {
      setRefining(false);
    }
  }

  return (
    <Panel className="rise p-4" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Eyebrow>
            Scene {cs.scene_order + 1} · {cs.type}
          </Eyebrow>
          <StatusBadge status={cs.status} />
        </div>
        {!hasImages && (
          <Button onClick={onGenerate} loading={busy}>
            Generate images
          </Button>
        )}
      </div>
      <p className="mt-2 text-sm text-muted">{cs.brief}</p>
      {triedButNoPreview && (
        <p className="mt-1 font-mono text-[0.7rem] text-faint">No previews available (mock mode)</p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cs.look_frames.map((f, i) => (
          <FrameCard
            key={f.id}
            f={f}
            index={i}
            aspect={aspect}
            busy={busy}
            refineActive={refineId === f.id}
            onPromote={onPromote}
            onRefineToggle={() => setRefineId((cur) => (cur === f.id ? null : f.id))}
          />
        ))}
      </div>
      {refineTarget && (
        <div className="mt-3 flex items-center gap-2 rounded-[var(--radius)] border border-accent/30 bg-bg-soft p-2">
          <Sparkles size={14} className="shrink-0 text-accent" aria-hidden />
          <label className="sr-only" htmlFor={`refine-${cs.id}`}>
            Refine instruction
          </label>
          <input
            id={`refine-${cs.id}`}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyRefine()}
            autoFocus
            placeholder="make the lighting golden hour, keep the subject…"
            className="min-w-0 flex-1 rounded border-none bg-transparent font-mono text-xs text-fg outline-none placeholder:text-faint"
          />
          <Button onClick={applyRefine} loading={refining} disabled={!instruction.trim()}>
            Refine
          </Button>
        </div>
      )}
    </Panel>
  );
}

function FrameCard({
  f,
  index,
  aspect,
  busy,
  refineActive,
  onPromote,
  onRefineToggle,
}: {
  f: LookFrame;
  index: number;
  aspect: string;
  busy: boolean;
  refineActive: boolean;
  onPromote: (frameId: string, target: string) => void;
  onRefineToggle: () => void;
}) {
  const playable = isPlayable(f.image_url);
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-[var(--radius)] border bg-bg-soft",
        refineActive ? "border-accent" : "border-border",
        aspectClass(aspect),
      )}
    >
      {playable ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={f.image_url!}
          alt={`Concept frame ${index + 1}`}
          title={f.prompt}
          className="size-full object-cover"
        />
      ) : busy ? (
        <div className="size-full shimmer" />
      ) : (
        <div className="flex size-full items-center justify-center p-2 text-center font-mono text-[0.6rem] text-faint">
          {f.prompt.slice(0, 60)}
        </div>
      )}
      {f.parent_frame_id && (
        <span
          className="absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[0.6rem] text-accent backdrop-blur"
          title="Refined from another frame"
        >
          <CornerDownRight size={10} aria-hidden /> refined
        </span>
      )}
      {playable && (
        <div
          className={cn(
            "absolute inset-x-0 bottom-0 flex font-mono text-[0.6rem] backdrop-blur transition-opacity",
            f.promoted_as === "none" && !refineActive
              ? "opacity-100 focus-within:opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
              : "opacity-100",
          )}
        >
          <button
            onClick={() => onPromote(f.id, "first_frame")}
            aria-label="Set as first frame"
            aria-pressed={f.promoted_as === "first_frame"}
            className={cn(
              "flex-1 py-2",
              f.promoted_as === "first_frame"
                ? "bg-accent/80 text-bg"
                : "bg-black/60 text-fg hover:bg-black/80",
            )}
          >
            {f.promoted_as === "first_frame" ? "★ frame" : "frame"}
          </button>
          <button
            onClick={() => onPromote(f.id, "character_ref")}
            aria-label="Cast as character"
            aria-pressed={f.promoted_as === "character_ref"}
            className={cn(
              "flex-1 border-l border-bg/40 py-2",
              f.promoted_as === "character_ref"
                ? "bg-accent/80 text-bg"
                : "bg-black/60 text-fg hover:bg-black/80",
            )}
          >
            {f.promoted_as === "character_ref" ? "★ cast" : "cast"}
          </button>
          <button
            onClick={onRefineToggle}
            aria-label="Refine this frame"
            aria-pressed={refineActive}
            className={cn(
              "flex-1 border-l border-bg/40 py-2",
              refineActive ? "bg-accent/80 text-bg" : "bg-black/60 text-accent hover:bg-black/80",
            )}
          >
            ✨ refine
          </button>
        </div>
      )}
    </div>
  );
}
