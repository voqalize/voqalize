/**
 * The concierge's face: idle, the STILL photo of the character persona.json
 * names (`src/characters/<character>.webp`); only once a call is up does the
 * live avatar mount, animated and turning. Nothing of the avatar runtime loads
 * while the page just sits there.
 *
 * To change the character, persona.json picks the photo too: add
 * `src/characters/<character>.webp` beside the others. With no photo for it,
 * the dock shows the name's initial.
 */
import { type ReactNode, useState } from "react";
import { PERSONA } from "../persona";

const STILLS = import.meta.glob<string>("../characters/*.webp", { eager: true, query: "?url", import: "default" });

/** The still photo's URL for the persona's character, or null when there is none. */
export const stillUrl: string | null = STILLS[`../characters/${PERSONA.character}.webp`] ?? null;

export function Face({ live, avatar }: { live: boolean; avatar: () => ReactNode }) {
  const [broken, setBroken] = useState(false);
  if (live) return <>{avatar()}</>;
  if (!stillUrl || broken) {
    return (
      <div className="face-placeholder" aria-hidden>
        <span>{PERSONA.initial}</span>
      </div>
    );
  }
  return <img className="face-still" src={stillUrl} alt={PERSONA.name} draggable={false} onError={() => setBroken(true)} />;
}
