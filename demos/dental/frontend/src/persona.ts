/**
 * The front-desk character, from ../persona.json — the one file the brain
 * reads too. Her name, face and languages are never written anywhere else in
 * this app: every "Talk to …", alt text and avatar `character` reads them here.
 */
import personaJson from "../../persona.json";
import { type Page, pageOf } from "./stage/nav";

export interface Persona {
  character: string;
  names: Record<string, string>;
  role: string;
  /** The label under her name in the dock and the call tile, per page. */
  roles?: Partial<Record<Page, string>>;
  languages: { code: string; label: string; short: string }[];
  default_language: string;
}

export const persona = personaJson as unknown as Persona;

export type Lang = string;
export const LANGS = persona.languages.map((l) => l.code);

/** Her name as said in `lang` (the default language's when there is none). */
export const nameIn = (lang?: string) => persona.names[lang ?? persona.default_language] ?? persona.names[persona.default_language];

/** The page's own copy is English; her name is the English one there. */
export const displayName = nameIn(persona.default_language);

/** The dock's and the tile's label for the page at `path` (persona.json `roles`). */
export const roleFor = (path: string): string => persona.roles?.[pageOf(path)] ?? persona.role;
