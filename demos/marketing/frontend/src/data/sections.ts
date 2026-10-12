/**
 * The section registry. One entry per section of the home page, in story order.
 * Read mode renders them top to bottom; Talk mode opens one at a time beside Tanvi.
 *
 * The data lives in `sections.json` so the brain (`../backend/site.py`) reads
 * the very same ids, titles and lines. Edit the JSON; this file only types it.
 *
 * `status` drives the visible placeholder treatment: a section stays labeled and
 * tinted until its review round is done (see docs/sections/README.md).
 */
import data from './sections.json';

export type SectionStatus = 'placeholder' | 'built';

export interface SectionDef {
  id: string;
  /** Title shown in nav and on the placeholder. */
  title: string;
  /** Suggestion chip label in Talk mode. */
  chip: string;
  /** What the visitor "said" when they tapped the chip. */
  said: string;
  /** What Tanvi says when she opens the section (simulated voice; the live brain words its own). */
  line: string;
  /** The question that keeps the conversation going after `line` (simulated voice, and the brain's fallback). */
  follow: string;
  /** Something to say once this section is open that works inside it (a tab, a switch); a target id from voice.json. */
  try?: { said: string; target: string };
  /** Routing words for typed requests in the simulated voice; the longest match wins. */
  keys: string[];
  /** Clicks Tanvi saves the visitor by opening this section. */
  clicks: number;
  status: SectionStatus;
  /** Notes file in docs/sections/. */
  notes: string;
  /** Placeholder tint (temporary, until the section is built). */
  tint: string;
  /** Concept ideas from the prototype, shown on the placeholder so we know what can go here. */
  ideas: string[];
}

export const SECTIONS = data as SectionDef[];

/** Picks the section whose longest matching keyword is longest. */
export function routeSection(text: string): SectionDef | null {
  const l = text.toLowerCase();
  let best: SectionDef | null = null;
  let bestLen = 0;
  for (const s of SECTIONS) {
    for (const k of s.keys) if (l.includes(k) && k.length > bestLen) { best = s; bestLen = k.length; }
  }
  return best;
}
