/**
 * The agent's character, read from `demos/university/persona.json`, the one
 * place it lives (the brain reads the same file). Nothing else in the page
 * names the character, its voice or its languages.
 */
import raw from "../../../persona.json";

export type Lang = "en" | "hi";

export interface Persona {
  character: string;
  name: string;
  gender: string;
  role: string;
  languages: Lang[];
  default_language: Lang;
  language_labels: Record<Lang, string>;
  language_names: Record<Lang, string>;
}

export const PERSONA = raw as unknown as Persona;
export const isLang = (x: unknown): x is Lang => typeof x === "string" && (PERSONA.languages as string[]).includes(x);
