/**
 * The holder: Javier's call, in an offscreen document of the extension
 * (`call.html`), so it lives through every page load on www.pcfactory.cl
 * (the site loads a page for every move between pages). The shared holder
 * from `@voqalize/stage/extension` does the call, the tabs, the relay to his
 * face and Stage (the timeline that fires his cues as he speaks, one result
 * per move); what is pcFactory's is here:
 *
 *   - a reply that opens on another page loads it as his voice starts, not
 *     at its first words: the store's pages take seconds to load;
 *   - the page a new tab opens on, when no pcFactory tab is open;
 *   - the two Actions the holder makes itself: `focus_tab` and
 *     `language_changed`;
 *   - the words for a call or a microphone that did not start.
 */

import { type HolderApi, type Job, startHolder } from "@voqalize/stage/extension";

import type { FocusTab, LanguageChanged } from "./actions.gen";
import { makeClient, micState, testHooks } from "./call-client";
import { failure, micFailure, ORIGIN, SITE } from "./site";

/** The moves that work on the cart or the checkout: a new tab opens on it. */
const CART_MOVES = new Set(["start_checkout", "apply_coupon", "commerce.cart_update", "commerce.cart_show"]);

/** The first page of a new tab, when no pcFactory tab is open. */
function firstPage(job: Job): string {
  if (job.kind !== "stage") return `${ORIGIN}/`;
  const args = (job.args ?? {}) as Record<string, unknown>;
  let path: unknown = "/";
  if (CART_MOVES.has(job.move)) path = "/carro";
  else if (job.move === "filter_listing") path = args.category_path;
  else if (job.move === "stores.show") path = "/tiendas";
  else if (job.move === "page.open" && Array.isArray(job.args)) path = job.args[0];
  else if (Array.isArray(job.args) && typeof job.args[1] === "string") path = job.args[1];
  else if (typeof args.path === "string") path = args.path;
  try {
    return new URL(typeof path === "string" && path ? path : "/", ORIGIN).href;
  } catch {
    return `${ORIGIN}/`;
  }
}

/** Whether `path` is another page than the one at `url`. */
function elsewhere(path: unknown, url: string | null): boolean {
  if (typeof path !== "string" || !path || !url) return false;
  try {
    const here = new URL(url);
    const there = new URL(path, here.origin);
    const strip = (p: string) => p.replace(/\/+$/, "") || "/";
    return strip(there.pathname) !== strip(here.pathname) || (Boolean(there.search) && there.search !== here.search);
  } catch {
    return false;
  }
}

startHolder(SITE, {
  makeClient,
  micState,
  firstPage,
  // A reply that opens on another page loads it while his voice starts: the
  // store takes seconds to load a page, and a little early is better than late.
  fireEarly: (cue, api) => cue.move === "page.open" && cue.before === 0 && elsewhere(cue.args[0], api.frontUrl()),
  // What a move read (prices, products, stock, the cart) answers him whichever
  // tab made it, as does the toggle.
  anyTab: ["language_requested", "prices_read", "products_found", "stock_read", "cart.changed"],
  holderCommands: {
    async focus_tab(payload) {
      const tab = Number((payload as FocusTab).tab_id);
      if (!Number.isInteger(tab)) return `no tab ${(payload as FocusTab).tab_id} to bring forward`;
      const got = (await chrome.runtime.sendMessage({ to: "sw", op: "focus_tab", tab }).catch(() => null)) as { ok?: boolean } | null;
      return got?.ok ? null : `no tab ${tab} to bring forward`;
    },
    // The brain's word that the call's language moved, by the toggle, by
    // voice or on request: the toggle follows at once, on every tab.
    async language_changed(payload, api: HolderApi) {
      api.setLanguage((payload as LanguageChanged).language);
      return null;
    },
  },
  micFailure,
  failure,
  testHooks,
});
