/**
 * The character, in ONE place: demos/insurance/persona.json, read by this page
 * and by the brain. Every "Talk to …", the face, the alt text and the language
 * toggle come from here. Change the character or add a language there, not here.
 */
import personaJson from "../../persona.json";

export interface PersonaLanguage {
  code: string;
  label: string;
  short: string;
}

interface PersonaFile {
  character: string;
  name: string;
  names: Record<string, string>;
  role: string;
  languages: PersonaLanguage[];
  default_language: string;
}

const file = personaJson as PersonaFile;

export const persona = {
  /** Display name, e.g. on "Talk to {name}". */
  name: file.name,
  /** The name in each language. */
  names: file.names,
  /** `@voqalize/avatar` character id. */
  character: file.character,
  role: file.role,
  /** The EN / हिंदी toggle's options, in order. */
  languages: file.languages.map(({ code, label, short }) => ({ code, label, short })),
  /** The toggle's starting position. */
  default: file.default_language,
} as const;

export type Lang = string;
