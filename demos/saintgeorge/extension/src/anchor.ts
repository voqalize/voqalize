/**
 * Runs at `document_start` on every page of saintgeorge.cl, in the extension's
 * isolated world, so the elements the adapter matches on are marked
 * `translate="no"` before Chrome's translator reaches them (see `anchors.ts`).
 * The DOM is shared with the page's world, where `content.ts` reads the marks.
 */

import { watchAnchors } from "./anchors";

watchAnchors();
