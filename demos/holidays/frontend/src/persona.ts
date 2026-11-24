/**
 * The trip planner's character, read from ../../persona.json — the one file
 * the brain reads too. Her name, face, the languages offered, the default and
 * the dock's label per page all come from there; nothing else on the page names
 * them. To change the character or add a language, edit persona.json only; the
 * still photo the idle dock shows is `src/characters/<character>.webp`.
 */
import raw from "../../persona.json";

export interface PersonaLanguage {
  label: string;
  name: string;
  voice: string;
}
/** The site's pages, as the dock labels them. */
export type Page = "home" | "plan" | "checkout" | "booked";
interface PersonaFile {
  character: string;
  name: string;
  role: string;
  roles?: Partial<Record<Page, string>>;
  default_language: string;
  languages: Record<string, PersonaLanguage>;
}

const p = raw as unknown as PersonaFile;

export const PERSONA = {
  character: p.character,
  name: p.name,
  role: p.role,
  roles: p.roles ?? {},
  initial: p.name.slice(0, 1),
  defaultLanguage: p.default_language,
  /** [tag, language] in the file's order: the toggle shows them so. */
  languages: Object.entries(p.languages).map(([tag, l]) => ({ tag, label: l.label, name: l.name })),
};

/** The page a path (inside the app's base) belongs to. */
export function pageOf(path: string): Page {
  const last = path.split("?")[0].replace(/\/$/, "").split("/").pop() || "home";
  return last === "plan" || last === "checkout" || last === "booked" ? last : "home";
}

/** The dock's role label for the page in front (persona.json `roles`). */
export const roleFor = (path: string): string => PERSONA.roles[pageOf(path)] ?? PERSONA.role;
