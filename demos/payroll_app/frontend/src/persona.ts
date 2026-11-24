/**
 * The character, from demos/payroll_app/persona.json — the one place it lives.
 * The avatar, the name on the call button ("Talk to {name}"), alt text and the
 * EN / हिंदी toggle all read it from here; the brain reads the same file. To
 * change the character, edit persona.json, never this app.
 */
import persona from "../../persona.json";

export interface Language {
  code: "en" | "hi";
  label: string;
  toggle: string;
}

export interface Persona {
  id: string;
  display_name: string;
  role: string;
  /** The dock's label per job (the brain's `mode_for`: /welcome onboarding, / and /help support, else coach). */
  roles: Record<Job, string>;
  avatar_character: string;
  voices: Record<string, string>;
  languages: Language[];
  default_language: Language["code"];
}

export type Job = "onboarding" | "support" | "coach";

export const PERSONA = persona as Persona;

/** The guide's job on an app path, by the same rule as the brain's `mode_for`. */
export function jobFor(path: string): Job {
  const p = `/${path.split("?")[0]!.replace(/^\/+|\/+$/g, "")}`;
  if (p.startsWith("/welcome")) return "onboarding";
  if (p === "/" || p === "/help" || p.startsWith("/help/")) return "support";
  return "coach";
}

/** The label under the name in the dock and the call tile, for the page in front. */
export const roleFor = (path: string): string => PERSONA.roles?.[jobFor(path)] ?? PERSONA.role;
