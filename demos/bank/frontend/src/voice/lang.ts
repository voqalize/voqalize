/**
 * The call's language, as the dock's toggle shows it. Before a call the toggle
 * sets it (and the call starts in it); during a call the toggle only asks
 * (`language_requested`) and the brain's `language_changed` moves it.
 */
import { create } from "zustand";
import { type Lang, persona } from "../persona";

const KEY = "anvaya-lang";

function stored(): Lang {
  try {
    const v = localStorage.getItem(KEY) as Lang | null;
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
      localStorage.setItem(KEY, lang);
    } catch {
      /* storage unavailable */
    }
    set({ lang });
  },
}));

/** The landing (CONTRACT.md mode) a path belongs to. */
export function landingOf(path: string): "banking" | "account" | "cards" | "loans" | "home" {
  if (path === "/app" || path.startsWith("/app/")) return "banking";
  if (path.startsWith("/open-account")) return "account";
  if (path === "/cards" || path.startsWith("/cards/")) return "cards";
  if (path === "/loans" || path.startsWith("/loans/")) return "loans";
  return "home";
}
