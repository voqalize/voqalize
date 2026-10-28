/**
 * Javier on Cannon Home — the page's half of the call.
 *
 * Cannon Home's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on cannonhome.cl (and www.cannonhome.cl, which
 * redirects to it). The shared page host from `@voqalize/stage/extension`
 * brings the corner widget with the Español/English toggle, his face (drawn
 * against a stand-in client fed by the holder), the call button, and Stage on
 * this page: the moves the holder sends here, made one at a time, each ringed
 * before it acts and answered once. What is Cannon Home's is the site adapter
 * (`cannonhome-actions.ts`): its moves, and its reports of every page the
 * visitor lands on, the product, listing, search dropdown, bag and delivery
 * form on it, whoever put them there.
 *
 * The call itself does not live here. It lives in the holder, an offscreen
 * document of the extension (`holder.ts`), which every Cannon Home page
 * follows; so a full page load here (Magento loads one for most moves)
 * changes nothing on the call.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/cannonhome/backend/`.
 *
 * The site's Content-Security-Policy would block the avatar runtime and our
 * API in the page's world; the extension removes that header on Cannon Home's
 * pages (`rules.json`).
 */

import { createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { defineSiteExtension } from "@voqalize/stage/extension";

import { cannonhome } from "./cannonhome-actions";
import { failure, SITE, SPOTLIGHT } from "./site";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";

defineSiteExtension({
  site: SITE,
  api: __VOQALIZE__,
  adapters: { "*": cannonhome },
  spotlight: SPOTLIGHT,
  // The black marquee (32 px, fixed on every width) and, on a phone, the
  // header under it.
  fixed: ["#topbarCannonBar", "header.page-header", ".nav-sections", ".sticky-header"],
  avatar: {
    // The holder's stand-in client, for whichever pipecat the avatar has.
    create: (mount, client) => createAvatar({ mount, client, character: CHARACTER }),
    preload: () => preloadAvatar(CHARACTER),
    still: async () => (await listCharacters()).find((c) => c.name === CHARACTER)?.still ?? null,
  },
  // `lang` only when the visitor chose it: the brain then holds to it
  // whatever they speak, and otherwise opens in Spanish and follows the
  // language they speak.
  sessionInit: ({ chosen, context }) => ({ surface: "cannonhome-ext", ...context, ...(chosen ? { lang: chosen } : {}) }),
  // What a move read (prices, the bag) answers him whichever tab made it, as
  // does the toggle.
  anyTab: ["language_requested", "prices_read", "cart.changed"],
  // What Cannon Home pins over its own pages, for the widget to keep clear
  // of: the WhatsApp button (bottom-right on a desktop, a left-edge tab on a
  // phone), the bag drawer (the right ~400 px, after every add), the filters
  // drawer (a 380 px left panel), and on a phone the sticky add-to-cart bar.
  obstacles: [
    { selector: "#whatsapp-link, .whatsapp-link-mobile, .new-whatsapp-mobile" },
    { selector: "aside.content-minicart-modal._show .modal-inner-wrap" },
    { selector: "#layered-filter-block.active" },
    { selector: "#sticky-addtocart-bar, .product-info-main .box-tocart", fixedOnly: true },
  ],
  // One microphone on the page: GoPersonal's voice search hides while he
  // listens (`page.ts` styleThePage).
  onCallState: (on) => document.documentElement.toggleAttribute("data-voqalize-call", on),
  consoleName: "__voqalizeCannonhome",
  failure,
});
