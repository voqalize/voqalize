/**
 * The extension's service worker: the shared one from
 * `@voqalize/stage/extension`, which makes the holder, opens and focuses tabs
 * for Javier's moves, opens the microphone grant in a tab of its own when the
 * widget's frame could not settle it, keeps each tab's move for its next page,
 * and keeps the visitor's language choice for both origins (with and without
 * `www.`). What is pcFactory's is where a tab he opens may point.
 */

import { startBackground } from "@voqalize/stage/extension";

import { SITE } from "./site";

startBackground(SITE, {
  /**
   * pcFactory's own pages and nothing else, whatever the brain sends: not the
   * checkout past Tipo de entrega (only /checkout and /checkout/tipo-entrega
   * open), not the login, account or registration pages, not a payment.
   */
  openable: [
    /^https:\/\/(www\.)?pcfactory\.cl(\/(?!checkout\/(?!tipo-entrega\/?(\?|#|$))|login|auth|realms|mi-cuenta|mis-compras|cuenta|registro|pago|webpay)[^\s]*)?$/i,
  ],
  justification: "Holds the voice call with Javier across PC Factory's page loads: the microphone, the WebRTC connection and his voice.",
});
