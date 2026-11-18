/**
 * Page-wide state: the EN / हिंदी toggle by the call button, and the router
 * binding the Stage performers navigate with.
 */
import { create } from "zustand";
import { persona } from "../persona";
import { emit } from "../stage/events";

interface UiState {
  lang: string;
  /** Navigate inside the app (set by <RouterBinding/>). */
  navigate: ((to: string) => void) | null;
  /** True while a call is live (set by the dock). */
  live: boolean;
}

export const useUi = create<UiState>(() => ({ lang: persona.default, navigate: null, live: false }));

/** The visitor moved the toggle: mid-call the brain is told, and moves both speech legs. */
export function chooseLanguage(lang: string) {
  if (useUi.getState().lang === lang) return;
  useUi.setState({ lang });
  if (useUi.getState().live) emit("site.language_chosen", { language: lang });
}

/** The brain moved both legs already (`site.language`): only the toggle follows. */
export function setLanguageFromAgent(lang: string) {
  useUi.setState({ lang });
}

export const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/** The path inside the app, without the base: "/quote/car". */
export function appPath(): string {
  const p = window.location.pathname;
  const rest = p.startsWith(BASE) ? p.slice(BASE.length) : p;
  return rest.replace(/\/+$/, "") || "/";
}

export function go(path: string) {
  if (appPath() === path) return;
  const nav = useUi.getState().navigate;
  if (nav) nav(path);
  else window.history.pushState(null, "", BASE + path);
}
