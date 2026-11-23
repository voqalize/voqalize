/**
 * The character, from `demos/fernhollow/persona.json` — the one file the
 * brain reads too. The page takes the avatar character, the display name, the
 * role label per page and the languages offered from here and nowhere else;
 * the voice is the brain's. To change the character, edit persona.json.
 */
import raw from "../../persona.json";

export interface Persona {
  character: string;
  name: string;
  role: string;
  /** The role label the dock shows, by the job of the page (CONTRACT.md v5/v6). */
  roles: Record<string, string>;
  voices: Record<string, string>;
  languages: string[];
  default_language: string;
}

export const persona: Persona = raw as Persona;

/** The job a page belongs to, as the brain picks it (backend/prompt.py LANDINGS). */
export function jobFor(path: string): string {
  const p = "/" + path.split("?")[0].replace(/^\/+|\/+$/g, "");
  if (p.startsWith("/orders/return")) return "returns";
  if (p.startsWith("/orders") || p.startsWith("/returns")) return "orders";
  if (p.startsWith("/gifts")) return "gifts";
  if (p.startsWith("/kiosk") || p.startsWith("/my-picks")) return "kiosk";
  return "shop";
}

/** The role label for a page: "Returns adviser" on a return form, "Design adviser" in the shop. */
export const roleFor = (path: string): string => persona.roles?.[jobFor(path)] ?? persona.role;

/** The label of a language on the toggle by the call button. */
export const LANGUAGE_LABEL: Record<string, string> = { en: "EN", hi: "हिंदी" };
