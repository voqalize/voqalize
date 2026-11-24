/**
 * The visitor's language, remembered across reloads (as on Paynora): the last
 * language used, picked on the toggle or moved to by the brain mid-call, is
 * kept in this browser and starts the toggle, so the next call's `init.lang`
 * (and a redial) start in it. Only a language persona.json offers is taken
 * back; storage that is blocked or full is ignored.
 */
import { LANGS, persona } from "./persona";

export const LANG_KEY = "dantika-lang";

const offered = (code: unknown): code is string => typeof code === "string" && LANGS.includes(code);

/** The language this browser last used here, or the persona's default. */
export function loadLang(): string {
  try {
    const saved = globalThis.localStorage?.getItem(LANG_KEY);
    if (offered(saved)) return saved;
  } catch {
    /* storage unavailable: the default */
  }
  return persona.default_language;
}

export function saveLang(code: string): void {
  if (!offered(code)) return;
  try {
    globalThis.localStorage?.setItem(LANG_KEY, code);
  } catch {
    /* storage unavailable: the choice lasts this page only */
  }
}
