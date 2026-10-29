/**
 * The extension's service worker: the shared one from
 * `@voqalize/stage/extension`, which makes the holder, opens and focuses tabs
 * for Javier's moves, opens the microphone grant in a tab of its own when the
 * widget's frame could not settle it, keeps each tab's move for its next page,
 * and keeps the visitor's language choice for both origins (with and without
 * `www.`). What is Cannon Home's is where a tab he opens may point.
 */

import { startBackground } from "@voqalize/stage/extension";

import { SITE } from "./site";

startBackground(SITE, {
  /**
   * Cannon Home's own pages (the bag and the checkout's delivery form, never
   * past it, its account pages or a payment), and WhatsApp, which the site
   * links as its sales chat. Nothing else, whatever the brain sends.
   */
  openable: [
    /^https:\/\/(www\.)?cannonhome\.cl(\/(?!checkout(?!\/cart\/?(\?|#|$)|\/?(\?|#shipping$|$))|customer\/account|onestepcheckout)|$)/i,
    /^https:\/\/(wa\.me|api\.whatsapp\.com)\//i,
  ],
  justification: "Holds the voice call with Javier across Cannon Home's page loads: the microphone, the WebRTC connection and his voice.",
});
