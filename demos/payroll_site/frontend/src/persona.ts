/**
 * The character, from demos/payroll_site/persona.json — the one place it
 * lives. The avatar, the name on the call button ("Talk to {name}"), alt text
 * and the EN / हिंदी toggle all read it from here; the brain reads the same
 * file (backend/persona.py). To change the character, edit persona.json.
 */
import persona from "../../persona.json";

export interface Language {
  code: string;
  label: string;
  toggle: string;
}

export const PERSONA = persona as {
  id: string;
  display_name: string;
  role: string;
  avatar_character: string;
  voices: Record<string, string>;
  languages: Language[];
  default_language: string;
};
