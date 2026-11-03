/**
 * Javier on the site — the page's half of the call.
 *
 * The site's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`) on every page of the site. The shared page host from
 * `@voqalize/stage/extension` brings the corner widget with the
 * Español/English toggle, his face (drawn against a stand-in client fed by
 * the holder), the call button, and Stage on this page: the moves the holder
 * sends here, made one at a time, each ringed before it acts and answered
 * once. What is the Site Agent's is the adapter (`adapter.ts`, the snippet's
 * watcher, executor and moves) and the agent itself (`agent.ts`: the site's
 * publishable key, embed.config, the session's `init`).
 *
 * The call lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so a full page load, a typed address or a second tab
 * changes nothing on it; the early shell (`shell.ts`) puts the widget back
 * the moment the next page shows.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and
 * the knowledge are the Site Agent's own, on the platform.
 */

import { createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { defineSiteExtension } from "@voqalize/stage/extension";

import { siteAgent, voice } from "./adapter";
import { agent, api, fallbackLanguage, servedLanguages, sessionInit } from "./agent";
import { ANY_TAB } from "./any-tab";
import { blocked, CHARACTER, failure, SITE, SITE_AGENT, SPOTLIGHT } from "./site";

defineSiteExtension({
  site: SITE,
  api,
  adapters: { "*": siteAgent() },
  spotlight: SPOTLIGHT,
  fixed: SITE_AGENT.fixed,
  obstacles: SITE_AGENT.obstacles,
  avatar: {
    // The holder's stand-in client, for whichever pipecat the avatar has; the
    // visitor's own turns, which the watcher's `screen_seen` and the
    // executor's yes-after-read-back hang on, are heard from it too.
    create: (mount, client) => {
      const started = () => voice.started();
      const stopped = () => voice.stopped();
      client.on("userStartedSpeaking", started);
      client.on("userStoppedSpeaking", stopped);
      const face = createAvatar({ mount, client, character: CHARACTER });
      return {
        destroy() {
          client.off("userStartedSpeaking", started);
          client.off("userStoppedSpeaking", stopped);
          face.destroy();
        },
      };
    },
    preload: () => preloadAvatar(CHARACTER),
    still: async () => (await listCharacters()).find((c) => c.name === CHARACTER)?.still ?? null,
  },
  // Spanish unless the visitor chose, and only where the site serves it: else
  // the site's own default, which is what the brain would open in anyway.
  pageLanguage: () => (agent.config ? (servedLanguages()[0] ?? fallbackLanguage()) : null),
  sessionInit: ({ language }) => ({ ...sessionInit(language) }),
  anyTab: ANY_TAB,
  onCallState: (on) => {
    document.documentElement.toggleAttribute("data-voqalize-call", on);
    if (on) dismiss();
  },
  consoleName: `__voqalize${SITE_AGENT.siteName.replace(/[^A-Za-z0-9]/g, "")}`,
  failure: (text, language) => {
    // Nothing to call with: why, in the visitor's words.
    if (text === "no agent configured") return blocked(agent.blocker ?? "no_config", language);
    // The configuration never came: read again for the next press.
    if (!agent.config) void agent.reload();
    return failure(text, language);
  },
});

/** What the site opens over its pages on a visit (an offer pop-up, say),
 *  closed by its own close button when a call starts, so it covers nothing
 *  he rings; and on each page the call goes on to, for a few seconds. */
function dismiss(): void {
  const selectors = SITE_AGENT.dismissOnCall ?? [];
  if (!selectors.length) return;
  const end = Date.now() + 8000;
  const look = () => {
    for (const s of selectors) {
      const el = document.querySelector<HTMLElement>(s);
      if (el && el.offsetParent !== null) el.click();
    }
    if (Date.now() < end) setTimeout(look, 500);
  };
  look();
}
