/**
 * The holder: Javier's call, in an offscreen document of the extension
 * (`call.html`), so it lives through every page load on cannonhome.cl
 * (Magento loads a page for most moves). The shared holder from
 * `@voqalize/stage/extension` does the call, the tabs, the relay to his face
 * and Stage (the timeline that fires his cues as he speaks, one result per
 * move); what is Cannon Home's is here:
 *
 *   - a reply that opens on another page loads it as his voice starts, not
 *     at its first words: the store's pages take seconds to load;
 *   - the page a new tab opens on, when no Cannon Home tab is open;
 *   - the two Actions the holder makes itself: `focus_tab` and
 *     `language_changed`;
 *   - the words for a call or a microphone that did not start.
 */

import { type HolderApi, type Job, startHolder } from "@voqalize/stage/extension";

import type { FocusTab, LanguageChanged } from "./actions.gen";
import { makeClient, micState, testHooks } from "./call-client";
import { failure, micFailure, ORIGIN, SITE } from "./site";

/** The moves that work on the bag or the checkout: a new tab opens on the bag. */
const BAG_MOVES = new Set(["start_checkout", "fill_checkout", "update_cart_item"]);

/** The first page of a new tab, when no Cannon Home tab is open. */
function firstPage(job: Job): string {
  if (job.kind !== "stage") return `${ORIGIN}/`;
  const args = (job.args ?? {}) as Record<string, unknown>;
  let path: unknown = "/";
  if (job.move === "filter_listing") path = args.category_path;
  else if (BAG_MOVES.has(job.move)) path = "/checkout/cart/";
  else if (job.move === "page.open" && Array.isArray(job.args)) path = job.args[0];
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
    const strip = (p: string) => p.replace(/\/+$/, "") || "/";
    return strip(new URL(path, here.origin).pathname) !== strip(here.pathname);
  } catch {
    return false;
  }
}

startHolder(SITE, {
  // Stage is typed against its own copy of pipecat: the same client.
  makeClient: (output, callbacks) => makeClient(output, callbacks as never) as never,
  micState,
  firstPage,
  // A reply that opens on another page loads it while his voice starts: the
  // store takes seconds to load a page, and a little early is better than late.
  fireEarly: (cue, api) => cue.move === "page.open" && cue.before === 0 && elsewhere(cue.args[0], api.frontUrl()),
  // What a move read (prices, the bag) answers him whichever tab made it, as
  // does the toggle.
  anyTab: ["language_requested", "prices_read", "cart_state"],
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
