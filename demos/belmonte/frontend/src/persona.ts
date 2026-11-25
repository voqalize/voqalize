/**
 * The concierge's character, read from ../../persona.json — the one file the
 * brain reads too. Her name, face, the languages offered, the default and the
 * dock's label per tab all come from there; nothing else in the app names
 * them. To change the character or add a language, edit persona.json only; the
 * still photo the idle dock shows is `src/characters/<character>.webp`.
 */
import raw from "../../persona.json";

export interface PersonaLanguage {
  label: string;
  name: string;
  voice: string;
}
/** The app's tabs, as the dock labels them. */
export type Tab = "home" | "dining" | "experiences" | "requests" | "stay" | "info";
interface PersonaFile {
  character: string;
  name: string;
  role: string;
  roles?: Partial<Record<Tab, string>>;
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

/** The tab a path (inside the app's base) belongs to. */
export function tabOf(path: string): Tab {
  const first = path.split("?")[0].replace(/^\/demos\/belmonte/, "").split("/").filter(Boolean)[0] ?? "";
  if (first === "dining" || first === "bar") return "dining";
  if (first === "spa" || first === "activities" || first === "meetings") return "experiences";
  if (first === "requests" || first === "visitors") return "requests";
  if (first === "stay") return "stay";
  if (first === "info") return "info";
  return "home";
}

/** The dock's role label for the tab in front (persona.json `roles`). */
export const roleFor = (path: string): string => PERSONA.roles[tabOf(path)] ?? PERSONA.role;
