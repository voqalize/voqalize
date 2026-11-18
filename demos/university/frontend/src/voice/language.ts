/**
 * The call's language: picked before the call by the toggle (it rides
 * `init.lang`), and kept in step mid-call both ways: the toggle sends
 * `language_requested`, and the brain's `language_changed` moves the toggle.
 */
import { create } from "zustand";
import { type Lang, PERSONA } from "../data/persona";

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
  lang: PERSONA.default_language,
  request: null,
  choose(lang) {
    if (lang === get().lang) return;
    set({ lang });
    get().request?.(lang);
  },
  follow: (lang) => set({ lang }),
}));
