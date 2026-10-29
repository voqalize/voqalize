/**
 * The extension's service worker: the shared one from
 * `@voqalize/stage/extension`, which makes the holder, opens and focuses tabs
 * for Javier's moves, opens the microphone grant in a tab of its own when the
 * widget's frame could not settle it, keeps each tab's move for its next page,
 * and keeps the visitor's language choice for both origins (with and without
 * `www.`). What is Agroplanet's is where a tab he opens may point.
 */

import { startBackground } from "@voqalize/stage/extension";

import { SITE } from "./site";

startBackground(SITE, {
  /**
   * Agroplanet's own pages and nothing else, whatever the brain sends: not
   * the registration, login (`/acceso-revision`), account or activation
   * pages, and not the quote's confirmation, which only the visitor's own
   * "Crear cotización" reaches.
   */
  openable: [
    /^https:\/\/(www\.)?agroplanet\.cl(\/(?!(registrate|acceso-revision|perfil|activar|cotizacion\/confirmacion)(\/|\?|#|$))[^\s]*)?$/i,
  ],
  justification: "Holds the voice call with Javier across Agroplanet's pages and reloads: the microphone, the WebRTC connection and his voice.",
});
