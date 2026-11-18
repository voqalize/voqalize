/**
 * The agent's character, read from `demos/property/persona.json` — the one
 * place it lives (the brain reads the same file). Nothing else in the page
 * names the character, its voice or its languages.
 */
import raw from "../../../persona.json";

export interface PersonaLanguage {
  tag: string;
  label: string;
  name: string;
}

export interface Persona {
  character: string;
  name: string;
  role: string;
  languages: PersonaLanguage[];
  default_language: string;
}

export const PERSONA = raw as unknown as Persona;
