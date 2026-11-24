/**
 * The agent's character, read from `demos/property/persona.json` — the one
 * place it lives (the brain reads the same file). Nothing else in the page
 * names the character, its voice or its languages. The idle dock's still
 * photo is `src/characters/<character>.webp` (see `voice/Face.tsx`).
 */
import raw from "../../../persona.json";

export interface PersonaLanguage {
  tag: string;
  label: string;
  name: string;
}

/** The agent's job on a page, by the brain's rule (`_job_of` in backend/brain.py). */
export type Job = "guide" | "booker";

export interface Persona {
  character: string;
  name: string;
  role: string;
  /** The label under the name in the dock and the call tile, per job. */
  roles: Record<Job, string>;
  languages: PersonaLanguage[];
  default_language: string;
}

export const PERSONA = raw as unknown as Persona;

/** A listing's page books a site visit; every other page is the guide's. */
export function jobFor(path: string): Job {
  return /^\/listing\/[A-Za-z]{3}-\d+/.test(path) ? "booker" : "guide";
}

/** The role label for the page in front. */
export const roleFor = (path: string): string => PERSONA.roles?.[jobFor(path)] ?? PERSONA.role;
