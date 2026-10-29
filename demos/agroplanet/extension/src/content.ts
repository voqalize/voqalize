/**
 * Javier on Agroplanet — the page's half of the call.
 *
 * Agroplanet's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on www.agroplanet.cl (and agroplanet.cl). The shared
 * page host from `@voqalize/stage/extension` brings the corner widget with
 * the Español/English toggle, his face (drawn against a stand-in client fed
 * by the holder), the call button, and Stage on this page: the moves the
 * holder sends here, made one at a time, each ringed before it acts and
 * answered once. What is Agroplanet's is the site adapter
 * (`agroplanet-actions.ts`): its moves, and its reports of every page the
 * visitor lands on, the product, listing, cart and quote form on it, whoever
 * put them there.
 *
 * Agroplanet is one Angular app: moving between its pages changes the route,
 * not the document, so this script, the widget (mounted outside `<app-root>`,
 * which the app never touches) and the call all stay as the visitor browses.
 * The call itself lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so a reload or a typed address changes nothing on it either.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and
 * the knowledge live in the brain, `demos/agroplanet/backend/`.
 *
 * agroplanet.cl sends no Content-Security-Policy, so the avatar runtime and
 * our API load in the page's world as they are; the extension changes no
 * header.
 */

import { createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { defineSiteExtension } from "@voqalize/stage/extension";

import { agroplanet } from "./agroplanet-actions";
import { acceptCookies, guardSplash } from "./page";
import { failure, SITE, SPOTLIGHT } from "./site";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";

defineSiteExtension({
  site: SITE,
  api: __VOQALIZE__,
  adapters: { "*": agroplanet },
  spotlight: SPOTLIGHT,
  // The compact header pins itself to the top (64 px) once the page is
  // scrolled past the full header; the rest of the header scrolls away.
  fixed: ["app-sticky-header-desktop mat-toolbar.shadow-sticky"],
  avatar: {
    // The holder's stand-in client, for whichever pipecat the avatar has.
    create: (mount, client) => createAvatar({ mount, client, character: CHARACTER }),
    preload: () => preloadAvatar(CHARACTER),
    still: async () => (await listCharacters()).find((c) => c.name === CHARACTER)?.still ?? null,
  },
  // `lang` only when the visitor chose it: the brain then holds to it
  // whatever they speak, and otherwise opens in Spanish and follows the
  // language they speak.
  sessionInit: ({ chosen, context }) => ({ surface: "agroplanet-ext", ...context, ...(chosen ? { lang: chosen } : {}) }),
  // What a move read (prices, products, stock, the cart) answers him whichever
  // tab made it, as does the toggle.
  anyTab: ["language_requested", "prices_read", "products_found", "stock_read", "cart.changed"],
  // What Agroplanet pins over its own pages, for the widget to keep clear of:
  // the cookie bar along the bottom (100 px, full width, until accepted), the
  // category menu's flyout, the mini-cart and the quote's selects (Material
  // overlays), and on a phone the product page's sticky buttons.
  obstacles: [
    { selector: ".cookies-wrapper", fixedOnly: true },
    { selector: "#acordeon-main mat-sidenav.mat-drawer-opened" },
    { selector: ".cdk-overlay-container .mat-menu-panel" },
    { selector: ".cdk-overlay-container .mat-select-panel" },
    { selector: "app-product-info .navbar", fixedOnly: true },
  ],
  // When a call starts, and on each page it carries on to: the home's empty
  // splash window closed (it locks scrolling), and watched for until ~10 s
  // after the load, since it opens a few seconds late; and the cookie bar's
  // "Entendido" pressed, so neither covers what he rings. The page's style
  // for the call is in `page.ts`.
  onCallState: (on) => {
    document.documentElement.toggleAttribute("data-voqalize-call", on);
    if (on) {
      guardSplash();
      acceptCookies();
    }
  },
  consoleName: "__voqalizeAgroplanet",
  failure,
});
