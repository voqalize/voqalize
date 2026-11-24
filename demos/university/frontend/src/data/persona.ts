/**
 * The agent's character, read from `demos/university/persona.json`, the one
 * place it lives (the brain reads the same file). Nothing else in the page
 * names the character, its voice or its languages.
 */
import raw from "../../../persona.json";

export type Lang = "en" | "hi";
export type Job = "advisor" | "counsellor";

export interface Persona {
  character: string;
  name: string;
  gender: string;
  role: string;
  /** The dock's label per job, for the page in front. */
  roles?: Partial<Record<Job, string>>;
  languages: Lang[];
  default_language: Lang;
  language_labels: Record<Lang, string>;
  language_names: Record<Lang, string>;
}

export const PERSONA = raw as unknown as Persona;
export const isLang = (x: unknown): x is Lang => typeof x === "string" && (PERSONA.languages as string[]).includes(x);

/** The agent's job on a route, by the same rule as the brain's `job_for` (backend/prompt.py). */
export function jobFor(path: string): Job {
  const p = `/${path.split("?")[0]!.replace(/^\/+|\/+$/g, "")}`;
  return ["/admissions", "/apply", "/scholarships", "/campus-life"].some((r) => p.startsWith(r)) ? "counsellor" : "advisor";
}

/** The label under the name in the dock and the call tile: the job on this page. */
export const roleFor = (path: string): string => PERSONA.roles?.[jobFor(path)] ?? PERSONA.role;
