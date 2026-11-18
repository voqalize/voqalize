/**
 * The character, from `demos/fernhollow/persona.json` — the one file the
 * brain reads too. The page takes the avatar character, the display name and
 * the languages offered from here and nowhere else; the voice is the brain's.
 * To change the character, edit persona.json.
 */
import raw from "../../persona.json";

export interface Persona {
  character: string;
  name: string;
  role: string;
  voices: Record<string, string>;
  languages: string[];
  default_language: string;
}

export const persona: Persona = raw as Persona;

/** The label of a language on the toggle by the call button. */
export const LANGUAGE_LABEL: Record<string, string> = { en: "EN", hi: "हिंदी" };
