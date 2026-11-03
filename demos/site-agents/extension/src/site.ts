/**
 * Who the site is, for every part of the extension: the site's own file
 * (`sites/<id>/site.ts`, bundled in as `@site`) with what every Site Agent
 * extension shares on top of it: Javier, Spanish (Chile) first and English,
 * and the widget's, grant page's and failures' words in both. Written once
 * here and handed to each entry point.
 *
 * The character, his name and the two languages are the extension's, whatever
 * the Site Agent's settings say: the demos are Javier, in Spanish or English.
 */

import type { GrantWords, WidgetWords } from "@voqalize/stage/extension";
import { defineSite } from "@voqalize/stage/extension";
import siteFile from "@site";

import type { SiteAgentSite } from "./site-agent";

const site: SiteAgentSite = siteFile;

export { site as SITE_AGENT };

export const CHARACTER = "javier";
export const NAME = "Javier";
/** The codes the toggle offers, in order. A call with no choice made opens in
 *  the first. */
export const LANGUAGES = ["es", "en"] as const;
export const ORIGIN = site.origin;
export const SPOTLIGHT = site.spotlight;
/** The extension as chrome://extensions names it. */
export const EXTENSION_NAME = `${NAME} para ${site.siteName}`;

const WORDS: Record<"es" | "en", WidgetWords> = {
  es: {
    invite: `Habla con ${NAME}`,
    role: "Tu guía por voz",
    inviteLabel: `Habla por voz con ${NAME}, el guía de ${site.siteName}`,
    minimise: "Minimizar",
    mute: "Silenciarme",
    unmute: "Activarme",
    muteLabel: `Silenciar tu micrófono en la llamada con ${NAME}`,
    hang: "Colgar",
    credit: "Voz de Voqalize · preview",
    language: "Idioma",
    connecting: "Conectando",
    failed: "No se pudo iniciar la llamada.",
    grant: `La primera vez, Chrome pide el micrófono para la extensión de ${NAME}.`,
    blocked: `Chrome bloquea el micrófono para la extensión «${EXTENSION_NAME}». En la configuración del micrófono, sácala de «No pueden usar el micrófono» y vuelve a llamar.`,
    settings: "Abrir la configuración",
    activity: { listening: "Escuchando", thinking: "Pensando", speaking: "Hablando" },
  },
  en: {
    invite: `Talk to ${NAME}`,
    role: "Your voice guide",
    inviteLabel: `Talk to ${NAME}, ${site.siteName}'s guide, by voice`,
    minimise: "Minimise",
    mute: "Mute me",
    unmute: "Unmute me",
    muteLabel: `Mute your microphone in the call with ${NAME}`,
    hang: "End call",
    credit: "Voice by Voqalize · preview",
    language: "Language",
    connecting: "Connecting",
    failed: "Could not start the call.",
    grant: `The first time, Chrome asks for the microphone for ${NAME}'s extension.`,
    blocked: `Chrome blocks the microphone for the “${EXTENSION_NAME}” extension. In the microphone settings, take it off “Not allowed to use your microphone”, then call again.`,
    settings: "Open the settings",
    activity: { listening: "Listening", thinking: "Thinking", speaking: "Speaking" },
  },
};

export const SITE = defineSite({
  id: site.id,
  matches: site.matches,
  home: `${ORIGIN}/`,
  opening: LANGUAGES[0],
  widget: {
    name: NAME,
    languages: LANGUAGES.map((code) => ({ code, label: code.toUpperCase() })),
    corner: site.corner,
    topClear: site.topClear,
    transitionName: `voqalize-${CHARACTER}`,
    theme: site.theme,
    words: {
      es: { ...WORDS.es, ...site.words?.es },
      en: { ...WORDS.en, ...site.words?.en },
    },
  },
});

export const GRANT_WORDS: Record<"es" | "en", GrantWords> = {
  es: {
    asking: `Chrome te pedirá usar el micrófono para ${NAME}. Elige «Permitir».`,
    tab: `Para que ${NAME} te escuche, Chrome te pedirá usar el micrófono. Elige «Permitir»; esta pestaña se cerrará sola.`,
    granted: `Listo: ${NAME} ya puede escucharte.`,
    refused: `Sin el micrófono ${NAME} no te escucha.`,
    again: "Permitir micrófono",
  },
  en: {
    asking: `Chrome will ask to use the microphone for ${NAME}. Choose “Allow”.`,
    tab: `So ${NAME} can hear you, Chrome will ask to use the microphone. Choose “Allow”; this tab closes by itself.`,
    granted: `Done: ${NAME} can hear you now.`,
    refused: `Without the microphone ${NAME} can't hear you.`,
    again: "Allow microphone",
  },
};

/** Why a call cannot start, as the page knows it before the call. */
export type Blocker = "no_key" | "no_config" | "unavailable";

const BLOCKED: Record<"es" | "en", Record<Blocker, string>> = {
  es: {
    no_key: "Esta extensión se armó sin la clave publicable del sitio (ver .env.example).",
    no_config: `No se pudo leer la configuración del agente de ${site.siteName}. Vuelve a intentarlo en un momento.`,
    unavailable: `El agente de ${site.siteName} no está disponible ahora.`,
  },
  en: {
    no_key: "This extension was built without the site's publishable key (see .env.example).",
    no_config: `Could not read the ${site.siteName} agent's configuration. Try again in a moment.`,
    unavailable: `The ${site.siteName} agent is not available right now.`,
  },
};

const lang = (language: string): "es" | "en" => (language === "en" ? "en" : "es");

export function blocked(why: Blocker, language: string): string {
  return BLOCKED[lang(language)][why];
}

/** Words for a call that did not start, in the call's language. */
export function failure(text: string, language: string): string {
  const lead = lang(language) === "en" ? "Could not start the call" : "No se pudo iniciar la llamada";
  return text.trim() ? `${lead}: ${text}` : `${lead}.`;
}

const MIC_WORDS: Record<"es" | "en", Record<string, string>> = {
  es: {
    permissions: `${NAME} no te escucha: Chrome bloquea el micrófono para la extensión. Permítelo y vuelve a empezar.`,
    "in-use": `${NAME} no te escucha: otra aplicación está usando el micrófono.`,
    "not-found": `${NAME} no te escucha: no se encontró un micrófono.`,
    other: `${NAME} no te escucha: el micrófono no se abrió.`,
  },
  en: {
    permissions: `${NAME} can't hear you: Chrome blocks the microphone for the extension. Allow it, then start again.`,
    "in-use": `${NAME} can't hear you: another app is using the microphone.`,
    "not-found": `${NAME} can't hear you: no microphone was found.`,
    other: `${NAME} can't hear you: the microphone did not open.`,
  },
};

/** Words for a microphone that did not open. */
export function micFailure(type: string, language: string): string {
  const words = MIC_WORDS[lang(language)];
  return words[type] ?? words.other!;
}
