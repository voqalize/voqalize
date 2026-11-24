/**
 * The call's language: picked before the call by the toggle (it rides
 * `init.lang`), and kept in step mid-call both ways: the toggle sends
 * `language_requested`, and the brain's `language_changed` moves the toggle.
 *
 * The last language used (picked on the toggle, or moved to by the brain
 * mid-call) is remembered in this browser, so a reload keeps it and the next
 * call starts in it (a redial keeps the brain's own). Only a language
 * persona.json offers is taken back; blocked or full storage is ignored.
 */
import { create } from "zustand";
import { type Lang, PERSONA, isLang } from "../data/persona";

export const LANG_KEY = "varenya-lang";

/** The language this browser last used here, or the persona's default. */
export function loadLang(): Lang {
  try {
    const saved = globalThis.localStorage?.getItem(LANG_KEY);
    if (isLang(saved)) return saved;
  } catch {
    /* storage unavailable: the default */
  }
  return PERSONA.default_language;
}

export function saveLang(lang: Lang): void {
  if (!isLang(lang)) return;
  try {
    globalThis.localStorage?.setItem(LANG_KEY, lang);
  } catch {
    /* storage unavailable: the choice lasts this page only */
  }
}

interface LanguageState {
  lang: Lang;
  /** Set by the live call: tells the brain the visitor asked for `lang`. */
  request: ((lang: Lang) => void) | null;
  /** The visitor pressed the toggle. */
  choose(lang: Lang): void;
  /** The brain says the call's language moved. */
  follow(lang: Lang): void;
}

export const useLanguage = create<LanguageState>((set, get) => ({
  lang: loadLang(),
  request: null,
  choose(lang) {
    if (lang === get().lang) return;
    set({ lang });
    get().request?.(lang);
  },
  follow: (lang) => set({ lang }),
}));

useLanguage.subscribe((s, prev) => {
  if (s.lang !== prev.lang) saveLang(s.lang);
});
