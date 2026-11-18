/**
 * The character, from demos/payroll_app/persona.json — the one place it lives.
 * The avatar, the name on the call button ("Talk to {name}"), alt text and the
 * EN / हिंदी toggle all read it from here; the brain reads the same file. To
 * change the character, edit persona.json, never this app.
 */
import persona from "../../persona.json";

export interface Language {
  code: "en" | "hi";
  label: string;
  toggle: string;
}

export interface Persona {
  id: string;
  display_name: string;
  role: string;
  avatar_character: string;
  voices: Record<string, string>;
  languages: Language[];
  default_language: Language["code"];
}

export const PERSONA = persona as Persona;
