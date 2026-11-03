/**
 * The holder: Javier's call, in an offscreen document of the extension
 * (`call.html`), so it lives through every reload and typed address on the
 * site, and across its tabs. The shared holder from
 * `@voqalize/stage/extension` does the call, the tabs, the relay to his face
 * and Stage (the timeline that fires his cues as he speaks, one result per
 * move). What is the Site Agent's is here: its brain speaks a little
 * differently from the demo brains the shared holder was written against, so
 * the client the holder gets translates.
 *
 *   - The toggle. The shared holder asks with a `language_requested` app
 *     event and shows the new language when the voice next speaks. The Site
 *     Agent's brain takes the visitor's pick as the client message
 *     `set_language {language}` (the snippet's language chips send the same),
 *     and answers with the Action `language_set`, its settings' name for the
 *     language the call is now in, both when it moved and when the voice tier
 *     refused and it went back. So the request is sent as that message, the
 *     toggle stays where it is until `language_set` comes (the holder's own
 *     early switch is put back at once), and a language the brain never
 *     confirms falls back on the toggle by itself after 4 s.
 *   - The languages the site serves. A page reports them once the brain hears
 *     it (`site_languages`, never sent on to the brain): a call that opened in
 *     one the site does not serve is in the site's default, and the toggle
 *     says so.
 *   - `language_set` itself is made here (it moves the toggle on every tab);
 *     every other Action of the brain's (`run_site_tool`, `read_site`,
 *     `open_page`, `open_item`, `open_listing`, `show_note`) goes to the tab
 *     in front, as the shared holder routes a site's own Actions.
 *   - A reply that opens another page (`site.page` on its first word) moves
 *     as the voice starts, not on its first words: a page takes a moment.
 */

import { type HolderApi, type HolderClient, startHolder } from "@voqalize/stage/extension";

import { makeClient, micState } from "./call-client";
import { SITE_LANGUAGES } from "./holder-events";
import { codeOf } from "./languages";
import { failure, LANGUAGES, micFailure, SITE } from "./site";

/** The Site Agent brain's client message for the visitor's pick. */
const SET_LANGUAGE = "set_language";

let api: HolderApi | null = null;
let served: string[] | null = null;

/** The holder's client, with the Site Agent's language wiring around it. */
function translated(client: HolderClient): HolderClient {
  const send = client.sendUIEvent.bind(client);
  client.sendUIEvent = (event: string, payload?: unknown) => {
    if (event === "language_requested") {
      const language = (payload as { language?: unknown } | null)?.language;
      if (typeof language === "string") client.sendClientMessage(SET_LANGUAGE, { language });
      // The holder has just armed its own switch on the next words: undone,
      // so only the brain's `language_set` moves the toggle.
      queueMicrotask(() => api?.setLanguage(api.state.language));
      return;
    }
    if (event === SITE_LANGUAGES) {
      const got = payload as { served?: unknown; fallback?: unknown } | null;
      served = Array.isArray(got?.served) ? got.served.filter((c): c is string => typeof c === "string") : null;
      const fallback = typeof got?.fallback === "string" ? got.fallback : null;
      if (api && served?.length && !served.includes(api.state.language) && fallback) api.setLanguage(fallback);
      return;
    }
    send(event, payload);
  };
  return client;
}

startHolder(SITE, {
  makeClient: (output, callbacks) => {
    served = null;
    return translated(makeClient(output, callbacks) as unknown as HolderClient);
  },
  micState,
  // A reply that opens on another page moves there while his voice starts.
  fireEarly: (cue) => cue.move === "site.page" && cue.before === 0,
  holderCommands: {
    // The brain's word that the call's language moved (by the toggle, by
    // voice, or back after a refusal): the toggle follows on every tab.
    async language_set(payload, holder) {
      const name = (payload as { language?: unknown } | null)?.language;
      const code = typeof name === "string" ? codeOf(name) : null;
      if (!code || !(LANGUAGES as readonly string[]).includes(code)) return `no toggle for the language ${String(name)}`;
      holder.setLanguage(code);
      return null;
    },
  },
  micFailure,
  failure,
  // The holder hands its own api over here once, at its start; the language
  // wiring above needs it outside a command.
  testHooks: (holder) => {
    api = (holder as { api?: HolderApi }).api ?? null;
  },
});
