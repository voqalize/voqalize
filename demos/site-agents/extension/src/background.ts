/**
 * The extension's service worker: the shared one from
 * `@voqalize/stage/extension`, which makes the holder, opens and focuses tabs
 * for Javier's moves, opens the microphone grant in a tab of its own when the
 * widget's frame could not settle it, keeps each tab's move for its next page,
 * and keeps the visitor's language choice for every host of the site. What is
 * the site's is where a tab he opens may point (its file's `openable`).
 */

import { startBackground } from "@voqalize/stage/extension";

import { NAME, SITE, SITE_AGENT } from "./site";

startBackground(SITE, {
  openable: SITE_AGENT.openable,
  justification: `Holds the voice call with ${NAME} across ${SITE_AGENT.siteName}'s pages and reloads: the microphone, the WebRTC connection and his voice.`,
});
