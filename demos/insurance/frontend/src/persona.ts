/**
 * The character, in ONE place: demos/insurance/persona.json, read by this page
 * and by the brain. The dock's name and role label, the still photo, the alt
 * text and the language toggle come from here. Change the character or add a
 * language there, not here.
 */
import personaJson from "../../persona.json";

export interface PersonaLanguage {
  code: string;
  label: string;
  short: string;
}

/** The guide's job on a page, by the same rule as the brain's `mode_of` (backend/store.py). */
export type Job = "home" | "quote" | "policies" | "claim";

interface PersonaFile {
  character: string;
  name: string;
  names: Record<string, string>;
  role: string;
  roles?: Partial<Record<Job, string>>;
  languages: PersonaLanguage[];
  default_language: string;
}

const file = personaJson as PersonaFile;

export const persona = {
  /** Display name, e.g. on "Talk to {name}". */
  name: file.name,
  /** The name in each language. */
  names: file.names,
  /** `@voqalize/avatar` character id; also names the still photo (src/characters/<id>.webp). */
  character: file.character,
  role: file.role,
  /** The EN / हिंदी toggle's options, in order. */
  languages: file.languages.map(({ code, label, short }) => ({ code, label, short })),
  /** The toggle's starting position when this browser has none saved. */
  default: file.default_language,
} as const;

export type Lang = string;

/** The job of an app path ("/quote/car" → quote), as the brain decides it. */
export function jobFor(path: string): Job {
  const p = path.split(/[?#]/)[0]!.replace(/^.*?\/demos\/insurance/, "").replace(/^\/+/, "");
  if (p.startsWith("quote") || p.startsWith("insurance")) return "quote";
  if (p.startsWith("my-policies")) return "policies";
  if (p.startsWith("claim")) return "claim";
  return "home";
}

/** The label under the name in the dock and on the call tile, for the page in front. */
export const roleFor = (path: string): string => file.roles?.[jobFor(path)] ?? file.role;
