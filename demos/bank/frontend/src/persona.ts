/**
 * The character, in ONE place: demos/bank/persona.json, read by this page and by
 * the brain. Change the character or add a language there, not here; the still
 * photo the idle dock shows is `src/characters/<character>.webp`.
 */
import personaJson from "../../persona.json";

export type Lang = "en" | "hi";

/** The assistant's job, by landing (CONTRACT.md modes). */
export type Landing = "banking" | "account" | "cards" | "loans" | "home";

export interface Persona {
  character: string;
  name: string;
  role: string;
  /** The label under the name in the dock and the call tile, per landing. */
  roles: Partial<Record<Landing, string>>;
  voices: Record<string, string>;
  languages: Lang[];
  default_language: Lang;
  language_labels: Record<string, string>;
  language_names: Record<string, string>;
}

export const persona = personaJson as Persona;

/** The landing (CONTRACT.md mode) a path belongs to. */
export function landingOf(path: string): Landing {
  const p = path.split("?")[0] ?? path;
  if (p === "/app" || p.startsWith("/app/")) return "banking";
  if (p.startsWith("/open-account")) return "account";
  if (p === "/cards" || p.startsWith("/cards/")) return "cards";
  if (p === "/loans" || p.startsWith("/loans/")) return "loans";
  return "home";
}

/** The dock's role label for the page in front (persona.json `roles`). */
export const roleFor = (path: string): string => persona.roles?.[landingOf(path)] ?? persona.role;
