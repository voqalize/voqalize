/**
 * The language the visitor picks before the call, and the `init` the call
 * starts with. The toggle shows only when the persona offers more than one
 * language (persona.json); the brain sets both speech legs from it.
 */
import { createElement } from "react";
import { create } from "zustand";
import { LANGUAGE_LABEL, persona } from "../persona";

export const useLang = create<{ lang: string }>(() => ({ lang: persona.default_language }));

/** The router path now, without the app's base: "/orders". */
export function currentLanding(): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const path = window.location.pathname.startsWith(base) ? window.location.pathname.slice(base.length) : window.location.pathname;
  return path || "/";
}

/** What the brain reads back as `session.init` (CONTRACT.md, v5). */
export function callInit(): Record<string, unknown> {
  return { surface: "fernhollow-web", landing: currentLanding(), lang: useLang.getState().lang };
}

export function LanguageToggle() {
  const lang = useLang((s) => s.lang);
  if (persona.languages.length < 2) return null;
  return createElement(
    "div",
    { className: "lang-toggle", role: "group", "aria-label": "Language" },
    persona.languages.map((code) =>
      createElement(
        "button",
        { key: code, type: "button", className: "chip", "aria-pressed": lang === code, onClick: () => useLang.setState({ lang: code }) },
        LANGUAGE_LABEL[code] ?? code.toUpperCase(),
      ),
    ),
  );
}
