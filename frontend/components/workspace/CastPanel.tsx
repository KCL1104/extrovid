"use client";

import { useState } from "react";
import { UserPlus, Users } from "lucide-react";
import { generateCast, generatePortraits, type Character } from "@/lib/api";
import { Button, EmptyState, Eyebrow, Panel, Pill } from "@/components/ui";
import { errMsg, isPlayable, usageChanged } from "@/components/workspace/shared";

const VIEWS = ["front", "side", "back"] as const;

export default function CastPanel({
  projectId,
  characters,
  hasScript,
  onChanged,
}: {
  projectId: string;
  characters: Character[];
  hasScript: boolean;
  onChanged: () => Promise<void> | void;
}) {
  const [extracting, setExtracting] = useState(false);
  const [portraitBusy, setPortraitBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function extract() {
    setExtracting(true);
    setError(null);
    try {
      await generateCast(projectId);
      await onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setExtracting(false);
    }
  }

  async function portraits(characterId: string) {
    setPortraitBusy(characterId);
    setError(null);
    try {
      await generatePortraits(projectId, characterId);
      usageChanged();
      await onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setPortraitBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Eyebrow>Cast</Eyebrow>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-faint">
            Planned characters with renderable features. Portrait sheets (front / side /
            back on white) anchor identity in every r2v generation — far stronger than
            in-scene look frames.
          </p>
        </div>
        <Button onClick={extract} loading={extracting} disabled={!hasScript}>
          <Users size={14} aria-hidden />
          {characters.length ? "Re-extract cast from script" : "Extract cast from script"}
        </Button>
      </div>

      {error && <p className="font-mono text-[0.75rem] text-fail">{error}</p>}

      {characters.length === 0 ? (
        <EmptyState
          title="No cast yet"
          hint={
            hasScript
              ? "Extract the cast from the script — characters get visualizable features the image and video models can actually render."
              : "Plan the production first; the cast is extracted from the script."
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {characters.map((c, i) => (
            <CharacterCard
              key={c.id}
              character={c}
              busy={portraitBusy === c.id}
              onPortraits={() => portraits(c.id)}
              delay={i * 40}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CharacterCard({
  character: c,
  busy,
  onPortraits,
  delay,
}: {
  character: Character;
  busy: boolean;
  onPortraits: () => void;
  delay: number;
}) {
  const portraits = c.portrait_image_urls ?? {};
  const hasSheet = VIEWS.some((v) => isPlayable(portraits[v]));
  return (
    <Panel className="rise p-4" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="title truncate text-xl text-fg">{c.name}</h3>
          {c.description && (
            <p className="mt-1 text-xs leading-relaxed text-muted">{c.description}</p>
          )}
          {(c.wardrobe_rules ?? []).length > 0 && (
            <p className="mt-1 font-mono text-[0.7rem] text-faint">
              wardrobe: {(c.wardrobe_rules ?? []).join("; ")}
            </p>
          )}
        </div>
        {hasSheet && <Pill className="shrink-0">turnaround ✓</Pill>}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        {VIEWS.map((view) => (
          <div key={view} className="min-w-0">
            <div className="aspect-[9/16] overflow-hidden rounded-[var(--radius)] border border-border bg-bg-soft">
              {isPlayable(portraits[view]) ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={portraits[view]}
                  alt={`${c.name} — ${view} view`}
                  className="size-full object-cover"
                />
              ) : (
                <div className="grid size-full place-items-center font-mono text-[0.6rem] text-faint">
                  {view}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <Button
          variant={hasSheet ? "default" : "primary"}
          onClick={onPortraits}
          loading={busy}
          className="w-full justify-center"
          title="Front view from features, side/back derived from the front so all three are the same person (3 image generations)"
        >
          <UserPlus size={14} aria-hidden />
          {hasSheet ? "Regenerate portrait sheet" : "Generate portrait sheet"}
        </Button>
      </div>
    </Panel>
  );
}
