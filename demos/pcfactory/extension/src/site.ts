/**
 * Who the site is, for every part of the extension: PC Factory's hosts, the
 * page a new tab opens on, the language a call opens in, and the widget's
 * words and colours. Written once here and handed to each entry point.
 */

import type { SpotlightTheme } from "@voqalize/stage";
import { defineSite } from "@voqalize/stage/extension";

/** The ring around what Javier points at: pcFactory's own bright blue
 *  (`--blue-semilight`, #3F59FA in the theme's `:root`). The site's green is
 *  too pale on its white product photos, and its near-black would read as
 *  part of the header; this blue holds on white (5:1) and on the near-black
 *  header and the comparator's dark bar (3.4:1), and the site uses it for
 *  nothing a ring would be mistaken for. */
export const RING = "#3F59FA";

/** 3 px of that blue, with its pulse, held 5.5 s unless the next ring
 *  replaces it. */
export const SPOTLIGHT: SpotlightTheme = {
  color: RING,
  width: 3,
  radius: 10,
  glow: `color-mix(in srgb, ${RING} 55%, transparent)`,
  holdMs: 5500,
};

export const ORIGIN = "https://www.pcfactory.cl";

// pcFactory's palette, read off the theme's `:root` and computed styles
// (2026-10-29): the header's near-black (`--black-dark`, #212425, the
// "Categorías" button and the main menu bar) for the card, the brand green
// (`--green-normal`, #43D87E, the price-range track and the promo band's
// family) for what the visitor presses, with the site's dark ink on it as its
// green buttons have; the dark grey of its "Agregar al carro" buttons
// (`--gray-dark`, #2E3538) for the raised parts; and the site's own face,
// Ubuntu, which every page has already loaded.
const SANS = `Ubuntu, Arial, system-ui, sans-serif`;

export const SITE = defineSite({
  id: "pcfactory",
  matches: ["https://www.pcfactory.cl/*", "https://pcfactory.cl/*"],
  home: `${ORIGIN}/`,
  // The store is Spanish (Chile): a call with no choice made opens in Spanish.
  opening: "es",
  widget: {
    name: "Javier",
    languages: [
      { code: "es", label: "ES" },
      { code: "en", label: "EN" },
    ],
    // pcFactory's own assistance button (#pcfAssistanceWrapper, the green
    // "pc" launcher of its chat and video advisers) owns the bottom-right.
    corner: "left",
    // Below the main menu bar, which pins itself to the top (86 px) as the
    // visitor scrolls up, for the last resort.
    topClear: 100,
    transitionName: "voqalize-javier",
    theme: {
      brand: "#43D87E",
      brandHover: "#51EE8F",
      onBrand: "#212425",
      card: "#212425",
      ink: "#ffffff",
      line: "rgba(255, 255, 255, 0.16)",
      muted: "rgba(255, 255, 255, 0.72)",
      raised: "#2E3538",
      live: "#43D87E",
      font: SANS,
      boldFont: SANS,
      radius: 4,
    },
    words: {
      es: {
        invite: "Habla con Javier",
        role: "Tu asesor por voz",
        inviteLabel: "Habla por voz con Javier, el asesor de PC Factory",
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
          "Chrome bloquea el micrófono para la extensión «Javier para PC Factory». En la configuración del micrófono, quítala de «No pueden usar el micrófono» y vuelve a llamar.",
        settings: "Abrir la configuración",
        activity: { listening: "Escuchando", thinking: "Pensando", speaking: "Hablando" },
      },
      en: {
        invite: "Talk to Javier",
        role: "Your voice adviser",
        inviteLabel: "Talk to Javier, PC Factory's adviser, by voice",
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
          "Chrome blocks the microphone for the “Javier para PC Factory” extension. In the microphone settings, take it off “Not allowed to use your microphone”, then call again.",
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
