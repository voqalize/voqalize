/**
 * The character, from demos/payroll_site/persona.json — the one place it
 * lives. The avatar, the name on the call button ("Talk to {name}"), alt text,
 * the EN / हिंदी toggle and the dock's role label all read it from here; the
 * brain reads the same file (backend/persona.py). To change the character,
 * edit persona.json.
 */
import persona from "../../persona.json";

export interface Language {
  code: string;
  label: string;
  toggle: string;
}

/** The brain's jobs, one per kind of page (backend/brain.py `job_of`). */
export type Job = "sdr" | "pricing" | "booker";

export const PERSONA = persona as {
  id: string;
  display_name: string;
  role: string;
  /** The dock's label for each job, so it says what the agent does on this page. */
  roles: Record<Job, string>;
  avatar_character: string;
  voices: Record<string, string>;
  languages: Language[];
  default_language: string;
};

/** The job the brain takes on a page: the same rule as `job_of` in brain.py. */
export function jobOf(path: string): Job {
  const p = path.replace(/^\/demos\/payroll_site/, "") || "/";
  if (p.startsWith("/pricing")) return "pricing";
  if (p.startsWith("/book-demo")) return "booker";
  return "sdr";
}

/** The role label the dock shows on a page. */
export const roleFor = (path: string): string => PERSONA.roles[jobOf(path)] ?? PERSONA.role;
