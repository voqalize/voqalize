/**
 * Who the site is, for every part of the extension: Cannon Home's hosts, the
 * page a new tab opens on, the language a call opens in, and the widget's
 * words and colours. Written once here and handed to each entry point.
 */

import type { SpotlightTheme } from "@voqalize/stage";
import { defineSite } from "@voqalize/stage/extension";

/** Cannon Home's "look here" colour: the deep red of every sale price
 *  (`.special-price .price`, #a01a1a in the theme's stylesheet). The brand's
 *  ink (#242128) is the colour of the text, so a dark ring would read as part
 *  of the page; the red reads on white, on the grey product photos and on the
 *  black bars. */
export const RING = "#a01a1a";

/** The ring around what Javier points at: 3 px of the sale red, with its
 *  pulse, held 5.5 s unless the next ring replaces it. */
export const SPOTLIGHT: SpotlightTheme = {
  color: RING,
  width: 3,
  radius: 10,
  glow: `color-mix(in srgb, ${RING} 55%, transparent)`,
  holdMs: 5500,
};

export const ORIGIN = "https://cannonhome.cl";

// Cannon Home's palette, read off the theme's stylesheet (styles-l.min.css):
// its ink (#242128, the text, the black "Buscar" and "Finalizar compra" pills
// and the marquee bar) for the card, the deep red of its sale prices for what
// the visitor presses; and the site's own face, Lato, which the page has
// already loaded.
const SANS = `Lato, "Helvetica Neue", Arial, system-ui, sans-serif`;

export const SITE = defineSite({
  id: "cannonhome",
  matches: ["https://cannonhome.cl/*", "https://www.cannonhome.cl/*"],
  home: `${ORIGIN}/`,
  // The store is Spanish (Chile): a call with no choice made opens in Spanish.
  opening: "es",
  widget: {
    name: "Javier",
    languages: [
      { code: "es", label: "ES" },
      { code: "en", label: "EN" },
    ],
    // The WhatsApp button owns the bottom-right on a desktop, and the bag
    // drawer slides in over the right after every add.
    corner: "left",
    // Below the fixed marquee bar (32 px; the header under it is fixed too on
    // a phone, ~100 px), for the last resort.
    topClear: 120,
    transitionName: "voqalize-javier",
    theme: {
      brand: "#A01A1A",
      brandHover: "#B82A29",
      onBrand: "#ffffff",
      card: "#242128",
      ink: "#ffffff",
      line: "rgba(255, 255, 255, 0.18)",
      muted: "rgba(255, 255, 255, 0.72)",
      raised: "#36323B",
      live: "#A01A1A",
      font: SANS,
      boldFont: SANS,
      radius: 8,
    },
    words: {
      es: {
        invite: "Habla con Javier",
        role: "Tu guía por voz",
        inviteLabel: "Habla por voz con Javier, el guía de Cannon Home",
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
          "Chrome bloquea el micrófono para la extensión «Javier para Cannon Home». En la configuración del micrófono, quítala de «No pueden usar el micrófono» y vuelve a llamar.",
        settings: "Abrir la configuración",
        activity: { listening: "Escuchando", thinking: "Pensando", speaking: "Hablando" },
      },
      en: {
        invite: "Talk to Javier",
        role: "Your voice guide",
        inviteLabel: "Talk to Javier, Cannon Home's guide, by voice",
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
          "Chrome blocks the microphone for the “Javier para Cannon Home” extension. In the microphone settings, take it off “Not allowed to use your microphone”, then call again.",
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
