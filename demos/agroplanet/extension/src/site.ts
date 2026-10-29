/**
 * Who the site is, for every part of the extension: Agroplanet's hosts, the
 * page a new tab opens on, the language a call opens in, and the widget's
 * words and colours. Written once here and handed to each entry point.
 */

import type { SpotlightTheme } from "@voqalize/stage";
import { defineSite } from "@voqalize/stage/extension";

/** The ring around what Javier points at: Agroplanet's own orange (#E65100,
 *  the page's `theme-color` and the logo's planet). The site's green
 *  (#AECA3A, every button) would read as one of its buttons and is too pale
 *  on white; its red menu bar (#CC0000) would vanish against the bar. The
 *  orange holds on white (3.8:1), on the green buttons and on the red bar,
 *  and the site rings nothing in it. */
export const RING = "#E65100";

/** 3 px of that orange, with its pulse, held 5.5 s unless the next ring
 *  replaces it. */
export const SPOTLIGHT: SpotlightTheme = {
  color: RING,
  width: 3,
  radius: 10,
  glow: `color-mix(in srgb, ${RING} 55%, transparent)`,
  holdMs: 5500,
};

export const ORIGIN = "https://www.agroplanet.cl";

// Agroplanet's palette, read off its computed styles (2026-10-29): the top
// bar's near-black (#212121) for the card, the brand green (#AECA3A, its
// "Agregar al carro", "Entendido" and every action button) for what the
// visitor presses, with dark ink on it for contrast (the site's white on that
// green is 2:1); a lifted grey for the raised parts; and the site's own face,
// Roboto, which every page has already loaded.
const SANS = `Roboto, "Helvetica Neue", Arial, system-ui, sans-serif`;

export const SITE = defineSite({
  id: "agroplanet",
  matches: ["https://www.agroplanet.cl/*", "https://agroplanet.cl/*"],
  home: `${ORIGIN}/`,
  // The store is Spanish (Chile): a call with no choice made opens in Spanish.
  opening: "es",
  widget: {
    name: "Javier",
    languages: [
      { code: "es", label: "ES" },
      { code: "en", label: "EN" },
    ],
    // The WhatsApp button, the scroll-to-top square and, on the quote form,
    // reCAPTCHA's badge own the bottom-right.
    corner: "left",
    // Below the compact header, which pins itself to the top (64 px) once
    // the page is scrolled, for the last resort.
    topClear: 80,
    transitionName: "voqalize-javier",
    theme: {
      brand: "#AECA3A",
      brandHover: "#BFD957",
      onBrand: "#1B1F0A",
      card: "#212121",
      ink: "#ffffff",
      line: "rgba(255, 255, 255, 0.16)",
      muted: "rgba(255, 255, 255, 0.72)",
      raised: "#2F2F2F",
      live: "#AECA3A",
      font: SANS,
      boldFont: SANS,
      radius: 6,
    },
    words: {
      es: {
        invite: "Habla con Javier",
        role: "Tu asesor por voz",
        inviteLabel: "Habla por voz con Javier, el asesor de Agroplanet",
        minimise: "Minimizar",
        mute: "Silenciarme",
        unmute: "Activarme",
        muteLabel: "Silenciar tu micrófono en la llamada con Javier",
        hang: "Colgar",
        credit: "Voz de Voqalize · preview",
        language: "Idioma",
        connecting: "Conectando",
        failed: "No se pudo iniciar la llamada.",
        grant: "La primera vez, Chrome pide el micrófono para la extensión de Javier.",
        blocked:
          "Chrome bloquea el micrófono para la extensión «Javier para Agroplanet». En la configuración del micrófono, quítala de «No pueden usar el micrófono» y vuelve a llamar.",
        settings: "Abrir la configuración",
        activity: { listening: "Escuchando", thinking: "Pensando", speaking: "Hablando" },
      },
      en: {
        invite: "Talk to Javier",
        role: "Your voice adviser",
        inviteLabel: "Talk to Javier, Agroplanet's adviser, by voice",
        minimise: "Minimise",
        mute: "Mute me",
        unmute: "Unmute me",
        muteLabel: "Mute your microphone in the call with Javier",
        hang: "End call",
        credit: "Voice by Voqalize · preview",
        language: "Language",
        connecting: "Connecting",
        failed: "Could not start the call.",
        grant: "The first time, Chrome asks for the microphone for Javier's extension.",
        blocked:
          "Chrome blocks the microphone for the “Javier para Agroplanet” extension. In the microphone settings, take it off “Not allowed to use your microphone”, then call again.",
        settings: "Open the settings",
        activity: { listening: "Listening", thinking: "Thinking", speaking: "Speaking" },
      },
    },
  },
});

/** Words for a call that did not start, in the call's language. */
export function failure(text: string, language: string): string {
  const lead = language === "en" ? "Could not start the call" : "No se pudo iniciar la llamada";
  return text.trim() ? `${lead}: ${text}` : `${lead}.`;
}

const MIC_WORDS: Record<string, Record<string, string>> = {
  es: {
    permissions: "Javier no te escucha: Chrome bloquea el micrófono para la extensión. Permítelo y vuelve a empezar.",
    "in-use": "Javier no te escucha: otra aplicación está usando el micrófono.",
    "not-found": "Javier no te escucha: no se encontró un micrófono.",
    other: "Javier no te escucha: el micrófono no se abrió.",
  },
  en: {
    permissions: "Javier can't hear you: Chrome blocks the microphone for the extension. Allow it, then start again.",
    "in-use": "Javier can't hear you: another app is using the microphone.",
    "not-found": "Javier can't hear you: no microphone was found.",
    other: "Javier can't hear you: the microphone did not open.",
  },
};

/** Words for a microphone that did not open. */
export function micFailure(type: string, language: string): string {
  const words = MIC_WORDS[language] ?? MIC_WORDS.es!;
  return words[type] ?? words.other!;
}
