/**
 * The trip planner's character, read from ../../persona.json — the one file
 * the brain reads too. Her name, face, the languages offered and the default
 * all come from there; nothing else on the page names them. To change the
 * character or add a language, edit persona.json only.
 */
import raw from "../../persona.json";

export interface PersonaLanguage {
  label: string;
  name: string;
  voice: string;
}
interface PersonaFile {
  character: string;
  name: string;
  role: string;
  default_language: string;
  languages: Record<string, PersonaLanguage>;
}

const p = raw as unknown as PersonaFile;

export const PERSONA = {
  character: p.character,
  name: p.name,
  role: p.role,
  initial: p.name.slice(0, 1),
  defaultLanguage: p.default_language,
  /** [tag, language] in the file's order: the toggle shows them so. */
  languages: Object.entries(p.languages).map(([tag, l]) => ({ tag, label: l.label, name: l.name })),
};
