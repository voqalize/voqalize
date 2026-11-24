/**
 * The call's language, as the EN / हिंदी toggle shows it. Before a call the
 * toggle sets it (and the call starts in it, `init.lang`); during a call a press
 * only asks (`language_requested`) and the brain's `language_changed` moves it.
 * The last language used, picked or moved to by the brain, is remembered in this
 * browser across reloads, so the next call (and a redial) starts in it.
 */
import { create } from "zustand";
import { type Lang, persona } from "../persona";
import { emit, isLive } from "./events";

export { landingOf } from "../persona";

export const LANG_KEY = "anvaya-lang";

function stored(): Lang {
  try {
    const v = localStorage.getItem(LANG_KEY) as Lang | null;
    if (v && persona.languages.includes(v)) return v;
  } catch {
    /* storage unavailable */
  }
  return persona.default_language;
}

export const useLang = create<{ lang: Lang; setLang: (l: Lang) => void }>((set) => ({
  lang: stored(),
  setLang: (lang) => {
    if (!persona.languages.includes(lang)) return;
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      /* storage unavailable: the choice lasts this page only */
    }
    set({ lang });
  },
}));

/** A press on the toggle: off a call it sets the language; on one it asks the brain. */
export function requestLanguage(lang: Lang) {
  if (lang === useLang.getState().lang) return;
  if (isLive()) emit("language_requested", { language: lang }, "visitor");
  else useLang.getState().setLang(lang);
}

/** The brain's `language_changed`: the toggle follows. */
export function languageChanged(payload: unknown) {
  const language = (payload as { language?: string } | null)?.language;
  if (language && (persona.languages as string[]).includes(language)) useLang.getState().setLang(language as Lang);
}
