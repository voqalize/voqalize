/**
 * Javier on PC Factory — the page's half of the call.
 *
 * pcFactory's pages are theirs and we change nothing in them. This script is
 * injected into the page's own JavaScript world (the manifest's
 * `"world": "MAIN"`), on www.pcfactory.cl (and pcfactory.cl, which redirects
 * to it). The shared page host from `@voqalize/stage/extension` brings the
 * corner widget with the Español/English toggle, his face (drawn against a
 * stand-in client fed by the holder), the call button, and Stage on this page:
 * the moves the holder sends here, made one at a time, each ringed before it
 * acts and answered once. What is pcFactory's is the site adapter
 * (`pcfactory-actions.ts`): its moves, and its reports of every page the
 * visitor lands on, the product, listing, cart and checkout step on it,
 * whoever put them there.
 *
 * The call itself does not live here. It lives in the holder, an offscreen
 * document of the extension (`holder.ts`), which every pcFactory page
 * follows; so a full page load here (the site loads one for every move
 * between pages) changes nothing on the call.
 *
 * Nothing here decides what Javier says or shows. The prompt, the tools and the
 * knowledge live in the brain, `demos/pcfactory/backend/`.
 *
 * pcfactory.cl sends no Content-Security-Policy, so the avatar runtime and our
 * API load in the page's world as they are; the extension changes no header.
 */

import { createAvatar, listCharacters, preloadAvatar } from "@voqalize/avatar";
import { defineSiteExtension } from "@voqalize/stage/extension";

import { pcfactory } from "./pcfactory-actions";
import { failure, SITE, SPOTLIGHT } from "./site";

declare const __VOQALIZE__: { apiBase: string; agentId: string; publishableKey: string };

const CHARACTER = "javier";

defineSiteExtension({
  site: SITE,
  api: __VOQALIZE__,
  adapters: { "*": pcfactory },
  spotlight: SPOTLIGHT,
  // The main menu bar pins itself to the top (86 px, `.scrolled-state`) as
  // the visitor scrolls up; the rest of the header scrolls away.
  fixed: ["#main-menu.scrolled-state", "#main-menu.menu-visible"],
  avatar: {
    // The holder's stand-in client, for whichever pipecat the avatar has.
    create: (mount, client) => createAvatar({ mount, client, character: CHARACTER }),
    preload: () => preloadAvatar(CHARACTER),
    still: async () => (await listCharacters()).find((c) => c.name === CHARACTER)?.still ?? null,
  },
  // `lang` only when the visitor chose it: the brain then holds to it
  // whatever they speak, and otherwise opens in Spanish and follows the
  // language they speak.
  sessionInit: ({ chosen, context }) => ({ surface: "pcfactory-ext", ...context, ...(chosen ? { lang: chosen } : {}) }),
  // What a move read (prices, products, stock, the cart) answers him whichever
  // tab made it, as does the toggle.
  anyTab: ["language_requested", "prices_read", "products_found", "stock_read", "cart.changed"],
  // What pcFactory pins over its own pages, for the widget to keep clear of:
  // the "Producto agregado" window after every add, the comparator's bar
  // along the bottom (228 px, full width), the categories window, and on a
  // phone the product page's sticky "Agregar al carro" bar.
  obstacles: [
    { selector: "#pcf-modal-added-product.show .modal-dialog" },
    { selector: "#pcf-comparator-summary.show" },
    { selector: "#categories-dropdown.show .modal-dialog" },
    { selector: ".add-to-cart-fixed", fixedOnly: true },
  ],
  // One voice on the page: pcFactory's own assistance button (its chat and
  // video advisers, bottom-right) hides while he is on the call (`page.ts`
  // styleThePage).
  onCallState: (on) => document.documentElement.toggleAttribute("data-voqalize-call", on),
  consoleName: "__voqalizePcfactory",
  failure,
});
