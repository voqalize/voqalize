/**
 * The character, in ONE place: demos/bank/persona.json, read by this page and by
 * the brain. Change the character or add a language there, not here.
 */
import personaJson from "../../persona.json";

export type Lang = "en" | "hi";

export interface Persona {
  character: string;
  name: string;
  role: string;
  voices: Record<string, string>;
  languages: Lang[];
  default_language: Lang;
  language_labels: Record<string, string>;
  language_names: Record<string, string>;
}

export const persona = personaJson as Persona;
