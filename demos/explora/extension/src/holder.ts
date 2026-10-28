/**
 * The holder: Javier's call, in an offscreen document of the extension
 * (`call.html`), so it lives through every page load on Explora's two hosts
 * and every load between them. The shared holder from
 * `@voqalize/stage/extension` does the call, the tabs, the relay to his face
 * and Stage (the timeline that fires his cues as he speaks, one result per
 * move); what is Explora's is here:
 *
 *   - the pacing of a page load against his voice: a `navigate` waits until
 *     the `after_words` words before it have been said, and a booking move
 *     that loads the booking site from www.explora.com waits for the sentence
 *     he is on. Neither host routes client-side, so either throws the page
 *     away; his voice plays here and never stops, but the page changes once he
 *     has said what leads to it, which is the pacing the brain is written
 *     against;
 *   - the site following the call's language (`language_changed`), once he
 *     has confirmed the switch aloud;
 *   - the words for a call that did not start, in the call's language.
 */

import { type HolderApi, type Job, QUIET_WAIT_MS, startHolder } from "@voqalize/stage/extension";

import type { LanguageChanged } from "./actions.gen";
import { makeClient, micState, testHooks } from "./call-client";
import { BOOKING_MOVES, bookingUrl, EXPLORA, MOVE, type NavigateArgs } from "./site";
import { onBookingSite, SITE } from "./site-language";

/** How long the site waits for him to finish confirming a language switch
 *  aloud before the page in front loads in the new language. Short on
 *  purpose: on dev call 1f6cd8ce the site followed the call to Spanish 11.7 s
 *  late, after the visitor had asked again. */
const SITE_SWITCH_CAP_MS = 3000;

/** Counts the page loads Javier sends, so a language switch still waiting for
 *  his voice gives way to a `navigate` that came after it. */
let navigations = 0;

const onBooking = (url: string) => {
  try {
    return onBookingSite(new URL(url).host);
  } catch {
    return false;
  }
};

/** Hold a move against his voice before it is sent to the page. */
async function pace(job: Job, when: "now" | "quiet" | null, api: HolderApi): Promise<void> {
  if (job.kind !== "stage") return;
  if (job.move === MOVE.navigate) {
    navigations++;
    await api.paced(Number((job.args as NavigateArgs).after_words ?? 0));
  } else if (BOOKING_MOVES.has(job.move) && !onBooking(api.frontUrl() ?? "") && bookingUrl(job.move, job.args, api.state.language)) {
    // A booking move from www.explora.com loads the booking site: let him
    // finish the sentence he is on first. One that needs a page already open
    // there (`choose_room`, `send_enquiry`) fails at once instead.
    await api.paced(0);
  } else if (when === "quiet") {
    await api.settle(QUIET_WAIT_MS, false);
  }
}

/**
 * The site follows the call's language: once he has confirmed the switch
 * aloud (he is speaking it as `language_changed` arrives), the page in front
 * loads its twin in that language (the adapter's own `site_language`, made on
 * the page, which knows its translations). A `navigate` that arrives
 * meanwhile wins: it lands in the new language anyway.
 */
async function followSite(next: string, api: HolderApi): Promise<void> {
  const seq = navigations;
  await api.settle(SITE_SWITCH_CAP_MS, true);
  if (!api.live() || navigations !== seq || api.state.language !== next) return;
  const why = await api.dispatch({ kind: "site", command: "site_language", payload: { language: next } });
  if (why) api.note(`the page stays in its language: ${why}`);
}

/** The first page of a new tab, when no Explora tab is open: the booking
 *  site's step, the page `navigate` names, else the home page. */
function firstPage(job: Job, api: HolderApi): string {
  if (job.kind !== "stage") return `${SITE}/`;
  const booking = bookingUrl(job.move, job.args, api.state.language);
  if (booking) return booking;
  const path = (job.args as Partial<NavigateArgs> | null)?.path;
  if (job.move === MOVE.navigate && typeof path === "string" && path) {
    try {
      return new URL(path, SITE).href;
    } catch {
      /* Not a path: the home page, where the move fails in words. */
    }
  }
  return `${SITE}/`;
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

startHolder(EXPLORA, {
  makeClient,
  micState,
  pace: (job, move, api) => pace(job, move?.when ?? null, api),
  firstPage,
  anyTab: ["language_requested", "enquiry_sent", "twin_lookup"],
  holderCommands: {
    // The brain's word that the call's language moved, by the toggle, by
    // voice or on request: the toggle follows at once, on every tab, and every
    // page of the call on both hosts takes it from here. At the call's start
    // it is only recorded (`stay`).
    async language_changed(payload, api) {
      const { language, site = "follow" } = payload as LanguageChanged;
      api.setLanguage(language);
      if (site !== "stay") void followSite(language, api);
      return null;
    },
  },
  micFailure: (type, language) => {
    const words = MIC_WORDS[language] ?? MIC_WORDS.en!;
    return words[type] ?? words.other!;
  },
  failure: (text, language) => {
    const lead = language === "es" ? "No se pudo iniciar la llamada" : "Could not start the call";
    return text.trim() ? `${lead}: ${text}` : `${lead}.`;
  },
  testHooks,
});
