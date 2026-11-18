/**
 * The language the visitor picked on the toggle beside the call button. The
 * choices and the default are persona.json's; the pick is remembered per
 * browser. It reaches the brain in the connect request's `init.lang`, and,
 * pressed during a call, as a `language_chosen` ui-event — the brain moves
 * both speech legs. The page never sets a voice or a language itself.
 */
import { create } from "zustand";
import { PERSONA } from "../persona";

const KEY = "wanderloom-lang";
function load(): string {
  try {
    const v = localStorage.getItem(KEY);
    if (v && PERSONA.languages.some((l) => l.tag === v)) return v;
  } catch {
    /* storage unavailable */
  }
  return PERSONA.defaultLanguage;
}
type Sender = ((language: string) => void) | null;
export const useLang = create<{ lang: string; sender: Sender }>(() => ({ lang: load(), sender: null }));
export function chooseLang(lang: string) {
  if (useLang.getState().lang === lang) return;
  useLang.setState({ lang });
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* storage unavailable */
  }
  useLang.getState().sender?.(lang);
}
