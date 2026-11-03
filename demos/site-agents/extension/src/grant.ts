/**
 * The extension's microphone grant, asked for once (`grant.html`): in the
 * widget's frame on the site, or in a tab of its own. The shared one from
 * `@voqalize/stage/extension`, with Javier's words.
 */

import { startGrant } from "@voqalize/stage/extension";

import { GRANT_WORDS, SITE } from "./site";

startGrant(GRANT_WORDS, SITE.opening);
