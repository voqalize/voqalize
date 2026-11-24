/**
 * The call's language, as the EN / हिंदी toggle shows it. The choices and the
 * default are persona.json's. Before a call the toggle sets it, and the call
 * starts in it (`init.lang`); during a call a press only asks the brain
 * (`language_chosen`), and the brain's `language_changed` moves the toggle —
 * also when the visitor switched by voice. The last language used is
 * remembered in this browser across reloads, so the next call (and a redial)
 * starts in it. The page never sets a voice or a language itself.
 */
import { create } from "zustand";
import { PERSONA } from "../persona";

export const LANG_KEY = "wanderloom-lang";

const offered = (v: string | null | undefined): v is string => !!v && PERSONA.languages.some((l) => l.tag === v);

function load(): string {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (offered(v)) return v;
  } catch {
    /* storage unavailable */
  }
  return PERSONA.defaultLanguage;
}

type Sender = ((language: string) => void) | null;
export const useLang = create<{ lang: string; sender: Sender }>(() => ({ lang: load(), sender: null }));

function setLang(lang: string) {
  useLang.setState({ lang });
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* storage unavailable: the choice lasts this page only */
  }
}

/** A press on the toggle: off a call it sets the language; on one it asks the brain. */
export function chooseLang(lang: string) {
  if (!offered(lang) || useLang.getState().lang === lang) return;
  const send = useLang.getState().sender;
  if (send) send(lang);
  else setLang(lang);
}

/** The brain's `language_changed`: the toggle follows, and remembers it. */
export function languageChanged(payload: unknown) {
  const language = (payload as { language?: string } | null)?.language;
  if (offered(language)) setLang(language);
}
