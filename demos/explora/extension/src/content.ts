/**
 * Javier on Explora — the page's half of the call.
 *
 * Explora's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`) on www.explora.com and reservations.explora.com, and
 * starts the shared page host from `@voqalize/stage/extension` with what is
 * Explora's:
 *
 *   - the site adapters, which register Javier's moves with Stage:
 *     `explora-actions.ts` on www.explora.com (sections, tabs, accordions,
 *     pages, a page's twin in the call's language) and
 *     `reservations-actions.ts` on the booking engine (a lodge's
 *     availability, a room, an expedition's enquiry). A move that belongs on
 *     the other host loads it, and the page it lands on finishes it;
 *   - the spotlight in Explora's terracotta, which rings everything he moves;
 *   - his face (the avatar, drawn against a stand-in client the holder feeds),
 *     and the session's `init` (where the visitor is, and the language).
 *
 * The call lives in the holder (`holder.ts`), which every Explora page on
 * both hosts follows, so a full page load, and a load from one host to the
 * other, changes nothing on the call. On the call button this page asks for
 * the extension's microphone the first time and mints the session with
 * `sessions.connect` (this page's fetch carries an Explora Origin, which the
 * publishable key allows), then hands it to the holder.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/explora/backend/`.
 */

import { createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { defineSiteExtension } from "@voqalize/stage/extension";

import { exploraAdapter } from "./explora-actions";
import { reservationsAdapter } from "./reservations-actions";
import { ANY_TAB, EXPLORA, RING } from "./site";
import { pageLanguage } from "./site-language";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";

defineSiteExtension({
  site: EXPLORA,
  api: __VOQALIZE__,
  adapters: {
    "www.explora.com": exploraAdapter,
    "explora.com": exploraAdapter,
    "reservations.explora.com": reservationsAdapter,
  },
  spotlight: { color: RING },
  fixed: ["header#masthead", ".explora-submenu.sticky-top"],
  avatar: {
    create: (mount, client) => createAvatar({ mount, client, character: CHARACTER }),
    // His face builds once the visitor reaches for the invite, not at page load.
    preload: () => preloadAvatar(CHARACTER),
    still: async () => (await listCharacters()).find((c) => c.name === CHARACTER)?.still ?? null,
  },
  // `lang` only when the visitor chose it: the brain then holds to it
  // whatever they speak, and otherwise follows the language they speak.
  // `site_lang`: the language the site is followed in from the start (the
  // visitor's choice, else the language of the page they are on), kept by the
  // holder for every page of the call on both hosts.
  sessionInit: ({ language, chosen, context }) => ({
    surface: "explora-ext",
    site: context.site,
    path: context.path,
    url: context.url,
    title: context.title,
    site_lang: language,
    ...(chosen ? { lang: chosen } : {}),
  }),
  pageLanguage,
  anyTab: ANY_TAB,
  // While a call is live, links to Explora stay in the tab Javier moves: a
  // new tab would follow the call too, but he moves the tab in front.
  keepLinksInTab: /^https:\/\/(www\.|reservations\.)?explora\.com(\/|$)/i,
  consoleName: "__voqalizeExplora",
});
