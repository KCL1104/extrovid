"use client";

import type { Character } from "@/lib/api";
import { cn } from "@/components/ui";
import { isPlayable } from "@/components/workspace/shared";

/** A cast member as a pinnable reference chip (Soul-ID / Ingredients pattern). Click to scope
 *  the Director to this character — "@Name" rides into the next instruction. */
export default function CastChip({
  character,
  selected = false,
  onToggle,
}: {
  character: Character;
  selected?: boolean;
  onToggle?: () => void;
}) {
  const portrait = character.reference_image_urls?.[0];
  const inner = (
    <>
      <span className="size-6 shrink-0 overflow-hidden rounded-full bg-bg-soft">
        {isPlayable(portrait) && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={portrait} alt={character.name} className="size-full object-cover" />
        )}
      </span>
      <span className="pr-1 text-xs text-fg">{character.name}</span>
    </>
  );

  if (!onToggle) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-border bg-panel px-2 py-1">
        {inner}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={selected}
      title={selected ? `Stop directing with ${character.name}` : `Direct with ${character.name}`}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2 py-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        selected
          ? "border-accent/60 bg-accent/10 ring-1 ring-accent/30"
          : "border-border bg-panel hover:border-border-hi",
      )}
    >
      {inner}
    </button>
  );
}
