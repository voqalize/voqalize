/**
 * The agent's character, read from `demos/fashio/persona.json` — the one
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

/** The agent's job on a page, by the brain's rule (`job_of` in backend/brain.py). */
export type Job = "shopping" | "fit" | "gifts" | "orders" | "returns" | "kiosk";

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

/** The job for a route under the app's base, as the brain picks it. */
export function jobFor(path: string): Job {
  if (/^\/p(\/|$)/.test(path)) return "fit";
  if (path.startsWith("/gifts")) return "gifts";
  if (path.startsWith("/orders")) return "orders";
  if (path.startsWith("/returns")) return "returns";
  if (path.startsWith("/kiosk")) return "kiosk";
  return "shopping";
}

/** The role label for the page in front. */
export const roleFor = (path: string): string => PERSONA.roles?.[jobFor(path)] ?? PERSONA.role;
