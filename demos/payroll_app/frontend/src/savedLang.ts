/**
 * The visitor's language, remembered across reloads (owner, round 2, R7: a
 * reload in the middle of a Hindi conversation put the toggle back on English,
 * and the next call answered Hindi in English). The last language used —
 * picked on the toggle, or moved to by the brain mid-call — is kept in this
 * browser and starts the toggle, and so the next call's `init.lang` (a
 * redial keeps the brain's own). Only a language persona.json offers is taken
 * back; storage that is blocked or full is ignored.
 */
import { PERSONA } from "./persona";

export const LANG_KEY = "payroll-app-lang";

const offered = (code: unknown): code is string => typeof code === "string" && PERSONA.languages.some((l) => l.code === code);

/** The language this browser last used here, or the persona's default. */
export function loadLang(): string {
  try {
    const saved = globalThis.localStorage?.getItem(LANG_KEY);
    if (offered(saved)) return saved;
  } catch {
    /* storage unavailable: the default */
  }
  return PERSONA.default_language;
}

export function saveLang(code: string): void {
  if (!offered(code)) return;
  try {
    globalThis.localStorage?.setItem(LANG_KEY, code);
  } catch {
    /* storage unavailable: the choice lasts this page only */
  }
}
